"""Everything the app window can ask for. Each method returns plain data (or {'error': ...})."""
import subprocess
import time
from datetime import datetime

import distill
import docs
import rules
from store import TUTOR_CLASS, COLORS
import watcher
from store import APP_DIR, new_id


def _err(e):
    return {'error': str(e)}


class Api:
    def __init__(self, app):
        self._app = app

    # ---------- helpers ----------
    @property
    def _store(self):
        return self._app.store

    def _pin_ok(self, pin):
        saved = self._store.data.get('pin') or ''
        return not saved or str(pin or '') == saved

    # ---------- overview ----------
    def state(self):
        s = self._store
        cls, asg = s.session_targets()
        today = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
        msgs = [e for e in s.read_log(2000) if 'result' in e and e.get('t', 0) >= today]
        classes = []
        for i, c in enumerate(s.data['classes']):
            c2 = {k: v for k, v in c.items() if k != 'source_text'}
            c2['color'] = c.get('color') if c.get('color') in COLORS else COLORS[i % len(COLORS)]
            c2['has_source'] = bool(c.get('source_text'))
            c2['assignments'] = [dict({k: v for k, v in a.items() if k != 'source_text'},
                                      has_source=bool(a.get('source_text'))) for a in c.get('assignments', [])]
            classes.append(c2)
        sess = None
        if cls:
            started = s.data['session'].get('started')
            ccolor = cls.get('color') if cls.get('color') in COLORS + ['ink'] else COLORS[0]
            sess = {'class_id': cls['id'], 'class': cls['name'], 'policy': cls.get('policy'), 'color': ccolor,
                    'assignment_id': asg['id'] if asg else None, 'assignment': asg['name'] if asg else '',
                    'started': started, 'elapsed': int(time.time() - started) if started else 0}
        return {
            'classes': classes,
            'tutor_mode': {k: v for k, v in TUTOR_CLASS.items() if k != 'policy_text'},
            'session': sess,
            'mode': s.data.get('mode', 'warn'),
            'has_pin': bool(s.data.get('pin')),
            'onboarded': bool(s.data.get('onboarded')),
            'extension': self._extension_status(),
            'engine': self._app.engine.status(),
            'perms': {'accessibility': watcher.has_accessibility(), 'watching': self._app.guard.watching},
            'ext_live': self._app.extension_seen_recently(),
            'stats': {'today': len(msgs), 'flagged': sum(1 for e in msgs if not e['result'].startswith('ok'))},
            'policy_labels': rules.POLICY_LABEL,
        }

    # ---------- session ----------
    def start_session(self, class_id, assignment_id, mode):
        if not self._store.cls(class_id):
            return _err('Pick a class first.')
        self._store.data['session'] = {'class_id': class_id, 'assignment_id': assignment_id or None, 'started': time.time()}
        self._store.data['mode'] = 'warn'
        self._store.save()
        c, a = self._store.session_targets()
        self._store.log({'t': time.time(), 'event': 'session start', 'class': c['name'],
                         'assignment': a['name'] if a else '', 'mode': self._store.data['mode']})
        self._app.refresh_menu()
        self._app.judge.warm(c, a)
        return self.state()

    def end_session(self, pin=''):
        if not self._pin_ok(pin):
            return _err('That PIN doesn\'t match.')
        c, _ = self._store.session_targets()
        self._store.data['session'] = None
        self._store.save()
        if c:
            self._store.log({'t': time.time(), 'event': 'session end', 'class': c['name']})
        self._app.refresh_menu()
        return self.state()

    def set_mode(self, mode, pin=''):
        if mode == 'warn' and self._store.data.get('mode') == 'block' and not self._pin_ok(pin):
            return _err('That PIN doesn\'t match.')
        self._store.data['mode'] = 'block' if mode == 'block' else 'warn'
        self._store.save()
        return self.state()

    def resolve_block(self, choice):
        return self._app.resolve_block(choice)

    def finish_onboarding(self):
        self._store.data['onboarded'] = True
        self._store.save()
        return self.state()

    # ---------- browser extension ----------
    def _ext_dir(self):
        from store import APP_DIR
        return APP_DIR / 'extension'

    def _extension_status(self):
        import shutil
        from pathlib import Path
        home = Path.home()
        browsers = []
        checks = [
            ('Google Chrome', home / 'Library/Application Support/Google/Chrome'),
            ('Microsoft Edge', home / 'Library/Application Support/Microsoft Edge'),
            ('Brave', home / 'Library/Application Support/BraveSoftware/Brave-Browser'),
            ('Arc', home / 'Library/Application Support/Arc'),
            ('Vivaldi', home / 'Library/Application Support/Vivaldi'),
        ]
        for name, path in checks:
            if path.exists():
                browsers.append(name)
        return {'installed_dir': str(self._ext_dir()) if self._ext_dir().exists() else '',
                'browsers': browsers}

    def prepare_extension(self):
        """Copy the bundled extension to a stable folder the user can load into their browser."""
        import shutil, sys, os
        from pathlib import Path
        dest = self._ext_dir()
        # source: alongside the app (bundled) or in the dev folder
        base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        src = Path(base) / 'extension'
        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            return {'ok': True, 'dir': str(dest)}
        except Exception as e:
            return {'error': str(e)}

    def open_extension_folder(self):
        import subprocess
        d = self._ext_dir()
        if not d.exists():
            self.prepare_extension()
        subprocess.Popen(['open', str(d)])
        return True

    def open_browser_extensions_page(self, browser):
        import subprocess
        pages = {
            'Google Chrome': 'com.google.Chrome',
            'Microsoft Edge': 'com.microsoft.edgemac',
            'Brave': 'com.brave.Browser',
        }
        # Best-effort: open the browser to its extensions page.
        urls = {'Google Chrome': 'chrome://extensions', 'Microsoft Edge': 'edge://extensions',
                'Brave': 'brave://extensions'}
        app_ids = pages.get(browser)
        try:
            if app_ids:
                subprocess.Popen(['open', '-b', app_ids, urls.get(browser, 'chrome://extensions')])
            return True
        except Exception as e:
            return {'error': str(e)}

    # ---------- documents ----------
    def choose_file(self):
        import webview
        kind = webview.FileDialog.OPEN if hasattr(webview, 'FileDialog') else webview.OPEN_DIALOG
        paths = self._app.window.create_file_dialog(
            kind, allow_multiple=False,
            file_types=('Documents (*.pdf;*.docx;*.txt;*.md)', 'All files (*.*)'))
        if not paths:
            return None
        return paths[0] if isinstance(paths, (list, tuple)) else paths

    def analyze(self, kind, name, path='', text='', class_id='', assignment_id=''):
        """kind: 'class' or 'assignment'. Uses the file, the pasted text, or the saved document."""
        try:
            if path:
                text = docs.extract_text(path)
            elif not (text or '').strip():
                c = self._store.cls(class_id)
                target = self._store.asg(c, assignment_id) if kind == 'assignment' else c
                text = (target or {}).get('source_text', '')
            return distill.analyze(self._app.engine, text, kind, name)
        except Exception as e:
            return _err(e)

    def save_class(self, draft):
        name = (draft.get('name') or '').strip()
        if not name:
            return _err('Give the class a name.')
        c = self._store.cls(draft.get('id')) if draft.get('id') else None
        if c is None:
            c = {'id': new_id(), 'assignments': []}
            self._store.data['classes'].append(c)
        c.update({'name': name, 'policy': draft.get('policy') or 'tutor',
                  'rules': self._clean_rules(draft.get('rules')), 'examples': self._clean_examples(draft.get('examples')),
                  'color': draft.get('color') if draft.get('color') in COLORS else c.get('color', COLORS[0]),
                  'policy_text': str(draft.get('policy_text', '')).strip()[:4000],
                  'category_reason': str(draft.get('category_reason', '')).strip()})
        if draft.get('source_text'):
            c['source_text'] = draft['source_text']
        self._store.save()
        self._app.judge.forget()
        self._app.refresh_menu()
        return self.state()

    def save_assignment(self, class_id, draft):
        c = self._store.cls(class_id)
        name = (draft.get('name') or '').strip()
        if not c or not name:
            return _err('Give the assignment a name.')
        a = self._store.asg(c, draft.get('id')) if draft.get('id') else None
        if a is None:
            a = {'id': new_id()}
            c.setdefault('assignments', []).append(a)
        a.update({'name': name, 'rules': self._clean_rules(draft.get('rules')),
                  'examples': self._clean_examples(draft.get('examples')),
                  'policy_text': str(draft.get('policy_text', '')).strip()[:3000]})
        if draft.get('source_text'):
            a['source_text'] = draft['source_text']
        self._store.save()
        self._app.judge.forget()
        return self.state()

    def delete_class(self, class_id, pin=''):
        if not self._pin_ok(pin):
            return _err('That PIN doesn\'t match.')
        s = self._store.data.get('session')
        if s and s.get('class_id') == class_id:
            return _err('End the study session for this class first.')
        self._store.data['classes'] = [c for c in self._store.data['classes'] if c['id'] != class_id]
        self._store.save()
        return self.state()

    def delete_assignment(self, class_id, assignment_id, pin=''):
        if not self._pin_ok(pin):
            return _err('That PIN doesn\'t match.')
        c = self._store.cls(class_id)
        if c:
            c['assignments'] = [a for a in c.get('assignments', []) if a['id'] != assignment_id]
            self._store.save()
        return self.state()

    @staticmethod
    def _clean_rules(items):
        out = []
        for r in items or []:
            rule = str(r.get('rule', '')).strip()
            if rule:
                out.append({'type': r.get('type') if r.get('type') in distill.TYPES else 'not_allowed',
                            'rule': rule, 'quote': str(r.get('quote', '')).strip()})
        return out

    @staticmethod
    def _clean_examples(items):
        out = []
        for e in items or []:
            p = str(e.get('prompt', '')).strip()
            if p:
                v = e.get('verdict') if e.get('verdict') in ('allow', 'warn', 'block') else 'warn'
                out.append({'prompt': p, 'verdict': v, 'why': str(e.get('why', '')).strip()})
        return out

    # ---------- testing the judge ----------
    def test_message(self, class_id, assignment_id, text):
        c = self._store.cls(class_id)
        if not c or not (text or '').strip():
            return _err('Pick a class and type a message.')
        a = self._store.asg(c, assignment_id)
        return self._app.judge.check(text.strip(), c, a, 'Try it page', timeout=30, use_cache=False)

    def accuracy_test(self, class_id, assignment_id):
        c = self._store.cls(class_id)
        if not c:
            return _err('Pick a class first.')
        return self._app.judge.accuracy_test(c, self._store.asg(c, assignment_id))

    # ---------- sessions (study history) ----------
    def sessions(self, limit=100):
        events = self._store.read_log()
        msgs = [e for e in events if 'result' in e]
        out, open_s = [], None
        for e in events:
            ev = e.get('event')
            if ev == 'session start':
                open_s = {'class': e.get('class', ''), 'assignment': e.get('assignment', ''),
                          'mode': e.get('mode', ''), 'start': e['t'], 'end': None}
            elif ev == 'session end' and open_s is not None:
                open_s['end'] = e['t']
                out.append(open_s); open_s = None
        if open_s is not None:
            open_s['end'] = None  # still running
            out.append(open_s)
        # attach counts per session from message timestamps
        for sdef in out:
            a, b = sdef['start'], (sdef['end'] or time.time())
            inwin = [m for m in msgs if a <= m['t'] <= b]
            sdef['checks'] = len(inwin)
            sdef['flagged'] = sum(1 for m in inwin if not m['result'].startswith('ok'))
            sdef['seconds'] = int((sdef['end'] or time.time()) - sdef['start'])
            sdef['live'] = sdef['end'] is None
        out.reverse()
        return out[:limit]

    # ---------- log ----------
    def get_log(self, limit=200):
        return list(reversed(self._store.read_log(limit)))

    def get_log_page(self, page=1, per_page=25):
        rows = list(reversed(self._store.read_log()))
        per_page = max(5, min(int(per_page or 25), 100))
        pages = max(1, -(-len(rows) // per_page))
        page = max(1, min(int(page or 1), pages))
        return {'rows': rows[(page - 1) * per_page: page * per_page], 'page': page, 'pages': pages,
                'total': len(rows), 'per_page': per_page}

    def export_log(self):
        import webview
        kind = webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG
        dest = self._app.window.create_file_dialog(kind, save_filename='AI Integrity Report.txt')
        if not dest:
            return None
        dest = dest[0] if isinstance(dest, (list, tuple)) else dest
        entries = self._store.read_log()
        msgs = [e for e in entries if 'result' in e]
        flagged = [e for e in msgs if not e['result'].startswith('ok')]
        lines = ['AI Integrity Guard report', f'Generated {datetime.now():%b %d %Y %I:%M %p}',
                 f'{sum(1 for e in entries if e.get("event") == "session start")} study sessions, '
                 f'{len(msgs)} AI messages, {len(flagged)} flagged', '']
        for e in entries:
            when = datetime.fromtimestamp(e['t']).strftime('%b %d %I:%M %p')
            if 'event' in e:
                lines.append(f'[{when}] --- {e["event"]}: {e.get("class", "")} {e.get("assignment", "")}')
            else:
                lines.append(f'[{when}] {e["where"]} | {e["class"]} {e.get("assignment", "")} | {e["result"].upper()}')
                lines.append(f'    "{e["text"]}"')
                if e.get('reasons'):
                    lines.append('    Why flagged: ' + ' '.join(e['reasons']))
            lines.append('')
        with open(dest, 'w') as f:
            f.write('\n'.join(lines))
        return dest

    def clear_log(self, pin=''):
        if not self._pin_ok(pin):
            return _err('That PIN doesn\'t match.')
        self._store.clear_log()
        return True

    # ---------- settings ----------
    def set_engine(self, backend, model='small', ollama_model=''):
        cfg = self._store.data['engine']
        cfg['backend'] = backend if backend in ('builtin', 'ollama', 'keywords') else 'builtin'
        cfg['model'] = model if model in ('small', 'large') else 'small'
        if ollama_model:
            cfg['ollama_model'] = ollama_model.strip()
        self._store.save()
        self._app.judge.forget()
        self._app.engine.override = None
        self._app.engine.start()
        return self.state()

    def set_pin(self, old_pin, new_pin):
        if not self._pin_ok(old_pin):
            return _err('The current PIN doesn\'t match.')
        new_pin = str(new_pin or '').strip()
        if new_pin and len(new_pin) < 4:
            return _err('Use at least 4 digits.')
        self._store.data['pin'] = new_pin
        self._store.save()
        return self.state()

    def remove_pin(self, pin):
        if not self._pin_ok(pin):
            return _err('That PIN doesn\'t match.')
        self._store.data['pin'] = ''
        self._store.save()
        return self.state()

    def open_accessibility_settings(self):
        watcher.has_accessibility(prompt=True)
        watcher.open_accessibility_settings()
        return True

    def open_data_folder(self):
        subprocess.Popen(['open', str(APP_DIR)])
        return True
