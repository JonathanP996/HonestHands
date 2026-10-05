"""Everything the app window can ask for. Each method returns plain data (or {'error': ...})."""
import subprocess
import time
from datetime import datetime, timedelta

import browsers as browserlib
import cloud as cloudlib
import extensions
import keepalive
import distill
import docs
import rules
from store import TUTOR_CLASS, COLORS
import watcher
from store import APP_DIR, new_id


def _err(e):
    return {'error': str(e)}


OVERRIDDEN = ('sent anyway', 'sent after warning')
RESULT_LABEL = {'ok': 'CLEAN', 'ok (disclose)': 'CLEAN (AI use to disclose)',
                'warned': 'FLAGGED', 'blocked': 'FLAGGED', 'sent anyway': 'OVERRIDDEN (SENT DESPITE WARNING)',
                'sent after warning': 'OVERRIDDEN (SENT DESPITE WARNING)'}


def kind_of(result):
    if result in OVERRIDDEN:
        return 'overridden'
    if result in ('warned', 'blocked'):
        return 'flagged'
    return 'clean' if str(result).startswith('ok') else 'other'


def dedupe(msgs, window=12):
    """One send can be logged by the keyboard guard, the click guard and the browser extension.
    Collapse identical entries (same text, site, result) that land within a few seconds."""
    out, last = [], {}
    for m in sorted(msgs, key=lambda e: e['t']):
        k = (m.get('text'), m.get('where'), m.get('result'))
        if k in last and m['t'] - last[k] < window:
            continue
        last[k] = m['t']
        out.append(m)
    return out


def tally(msgs):
    """clean (anything that went through fine) / flagged (stopped) / overridden (sent despite a warning)."""
    res = [kind_of(m['result']) for m in dedupe(msgs)]
    over, warned = res.count('overridden'), res.count('flagged')
    return {'clean': res.count('clean'), 'overridden': over,
            'flagged': max(0, warned - over)}   # every overridden send was warned first; don't count it twice


SITE_NAMES = (('gemini', 'Gemini'), ('chatgpt', 'ChatGPT'), ('openai', 'ChatGPT'), ('claude', 'Claude'),
              ('deepseek', 'DeepSeek'), ('perplexity', 'Perplexity'), ('copilot', 'Copilot'), ('grok', 'Grok'),
              ('meta', 'Meta AI'), ('mistral', 'Mistral'), ('poe', 'Poe'), ('aistudio', 'AI Studio'),
              ('notebooklm', 'NotebookLM'))


def site_name(where):
    w = (where or '').lower()
    for key, nice in SITE_NAMES:
        if key in w:
            return nice
    return (where or 'Other').replace('www.', '')


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
                    'started': started, 'elapsed': int(time.time() - started) if started else 0,
                    'ends_at': s.data['session'].get('ends_at'), 'locked': bool(s.data['session'].get('locked')),
                    'minutes': s.data['session'].get('minutes') or 0,
                    # counts for THIS session only (everything logged since it started)
                    'stats': tally([e for e in s.read_log() if 'result' in e and e['t'] >= (started or 0)])}
        return {
            'classes': classes,
            'tutor_mode': {k: v for k, v in TUTOR_CLASS.items() if k != 'policy_text'},
            'session': sess,
            'mode': s.data.get('mode', 'warn'),
            'has_pin': bool(s.data.get('pin')),
            'onboarded': bool(s.data.get('onboarded')),
            'extension': self._extension_status(),
            'browser': {'chosen': s.data.get('browser', ''), 'options': browserlib.options()},
            'lock': dict({'browsers': True, 'ai_apps': False}, **(s.data.get('lock') or {})),
            'engine': self._app.engine.status(),
            'perms': {'accessibility': watcher.has_accessibility(), 'watching': self._app.guard.watching},
            'ext_live': self._app.extension_seen_recently(),
            'stats': dict(tally(msgs), today=len(msgs)),
            'policy_labels': rules.POLICY_LABEL,
            'exit': self._app.cloud.exit_paths(), 'inbox': self._app.cloud.inbox,
            'now': time.time(),
            'cloud_user': {'signed_in': self._app.cloud.signed_in, 'name': self._app.cloud.c.get('display_name') or ''},
        }

    # ---------- session ----------
    def start_session(self, class_id, assignment_id, mode, minutes=0):
        if not self._store.cls(class_id):
            return _err('Pick a class first.')
        try:
            minutes = int(minutes or 0)
        except (TypeError, ValueError):
            minutes = 0
        if minutes < 0 or minutes > 12 * 60:
            return _err('Choose a lock-in between 1 minute and 12 hours.')
        if minutes:
            # a timed lock can only be started if there is a way out, so nobody can trap themselves
            if not self._store.data.get('pin'):
                try:
                    self._app.cloud.releasers()               # refresh the friend count right now
                except Exception:
                    pass
            ex = self._app.cloud.exit_paths()
            if not ex['pin'] and not ex['friends']:
                return _err('To lock in for a set time you need a way out for emergencies: set an accountability PIN in Settings, '
                            'or invite a friend who can release you in Community.')
        now = time.time()
        sess = {'class_id': class_id, 'assignment_id': assignment_id or None, 'started': now}
        if minutes:
            sess.update(ends_at=now + minutes * 60, locked=True, minutes=minutes)
        self._store.data['session'] = sess
        self._store.data['mode'] = 'warn'
        self._store.save()
        c, a = self._store.session_targets()
        self._store.log({'t': now, 'event': 'session start', 'class': c['name'],
                         'assignment': a['name'] if a else '', 'mode': self._store.data['mode'], 'minutes': minutes})
        if minutes:
            keepalive.install()                              # a watcher that relaunches the app if it is force-quit
        self._app.refresh_menu()
        self._app.ai_guard.warm(c, a)
        return self.state()

    def _finish_session(self, reason='', ended_by=''):
        """Ends the running session (and the lock, and its watcher). Used by every way a session can end."""
        c, _ = self._store.session_targets()
        self._store.data['session'] = None
        self._store.save()
        keepalive.remove()
        if c:
            e = {'t': time.time(), 'event': 'session end', 'class': c['name']}
            if reason:
                e['reason'] = reason
            self._store.log(e)
        self._app.refresh_menu()
        if ended_by:
            import watcher
            watcher.notify('HonestHands', ended_by)

    def finish_if_due(self):
        """Ends a timed lock-in whose time is up. True if it did."""
        s = self._store.data.get('session') or {}
        if s.get('ends_at') and time.time() >= s['ends_at']:
            self._finish_session('time was up', ended_by='Your lock-in is complete. Nicely done.')
            return True
        return False

    def end_session(self, pin=''):
        if self._app.locked_now():
            saved = self._store.data.get('pin')
            end = datetime.fromtimestamp(self._store.data['session']['ends_at']).strftime('%-I:%M %p')
            if not saved:
                return _err(f'This lock-in runs until {end}. You can leave early only if a friend releases you.')
            if str(pin or '') != saved:
                return _err('That PIN doesn\'t match.')
            self._finish_session('ended early with the PIN')
            return self.state()
        if not self._pin_ok(pin):
            return _err('That PIN doesn\'t match.')
        self._finish_session()
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
    def _chosen(self):
        return self._store.data.get('browser') or ''

    def _ext_dir(self):
        key = self._chosen() or 'chrome'
        return extensions.dest_for(browserlib.BROWSERS[key]['kind'])

    def _extension_status(self):
        d = self._ext_dir()
        key = self._chosen()
        have = d.exists() and (any(d.glob('*.app')) if key == 'safari' else (d / 'manifest.json').exists())
        return {'installed_dir': str(d) if have else '', 'kind': browserlib.BROWSERS[key]['kind'] if key else ''}

    def set_browser(self, key):
        if key not in browserlib.BROWSERS:
            return _err('Pick one of the listed browsers.')
        self._store.data['browser'] = key
        self._store.save()
        return self.state()

    def prepare_extension(self, key=None):
        """Builds the extension for the chosen browser (a folder for Chrome/Edge/Firefox, a small helper app for Safari)."""
        key = key or self._chosen()
        if key not in browserlib.BROWSERS:
            return _err('Choose your browser first.')
        try:
            r = extensions.prepare(browserlib.BROWSERS[key]['kind'])
            return dict(r, ok=True)
        except Exception as e:
            return _err(e)

    def open_extension_folder(self):
        import subprocess
        d = self._ext_dir()
        if not d.exists():
            self.prepare_extension()
        key = self._chosen()
        # show the folder itself, selected in Finder, so it is obvious which one to pick in the browser
        subprocess.Popen(['open', '-R', str(d)] if key != 'safari' else ['open', str(d)])
        return True

    def set_lock(self, browsers_on, ai_apps_on):
        self._store.data['lock'] = dict(self._store.data.get('lock') or {}, browsers=bool(browsers_on), ai_apps=bool(ai_apps_on))
        self._store.save()
        return self.state()

    def launch_extension_app(self):
        import subprocess
        d = self._ext_dir()
        app = next(iter(d.glob('*.app')), None) if d.exists() else None
        if not app:
            return _err('Build the Safari extension first.')
        subprocess.Popen(['open', str(app)])
        return True

    def open_browser_extensions_page(self, key=None):
        """Opens the chosen browser on its extensions page (Safari has none to deep-link, so it just opens)."""
        import subprocess
        key = key if key in browserlib.BROWSERS else self._chosen()
        if key not in browserlib.BROWSERS:
            return _err('Choose your browser first.')
        info = browserlib.BROWSERS[key]
        try:
            subprocess.Popen(['open', '-b', info['bundle']] + ([info['page']] if info['page'] else []))
            return True
        except Exception as e:
            return _err(e)

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
        self._app.ai_guard.forget()
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
        self._app.ai_guard.forget()
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

    # ---------- testing the guard ----------
    def test_message(self, class_id, assignment_id, text):
        c = self._store.cls(class_id)
        if not c or not (text or '').strip():
            return _err('Pick a class and type a message.')
        a = self._store.asg(c, assignment_id)
        return self._app.ai_guard.check(text.strip(), c, a, 'Try it page', timeout=30, use_cache=False)

    def accuracy_test(self, class_id, assignment_id):
        c = self._store.cls(class_id)
        if not c:
            return _err('Pick a class first.')
        return self._app.ai_guard.accuracy_test(c, self._store.asg(c, assignment_id))

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
            sdef.update(tally(inwin))
            sdef['id'] = sdef['start']
            c = next((x for x in self._store.data['classes'] if x['name'] == sdef['class']), None)
            sdef['color'] = 'ink' if sdef['class'] == 'Tutor mode' else ((c or {}).get('color') or 'lav')
            sdef['seconds'] = int((sdef['end'] or time.time()) - sdef['start'])
            sdef['live'] = sdef['end'] is None
        out.reverse()
        return out[:limit]

    # ---------- log ----------
    def get_log(self, limit=200):
        return list(reversed(self._store.read_log(limit)))

    def get_log_page(self, page=1, per_page=25, kind='all'):
        allrows = list(reversed(self._store.read_log()))
        counts = {'all': len(allrows), 'flagged': 0, 'overridden': 0, 'clean': 0}
        for r in allrows:
            if 'result' in r:
                counts[kind_of(r['result'])] = counts.get(kind_of(r['result']), 0) + 1
        rows = allrows if kind == 'all' else [r for r in allrows if 'result' in r and kind_of(r['result']) == kind]
        per_page = max(5, min(int(per_page or 25), 100))
        pages = max(1, -(-len(rows) // per_page))
        page = max(1, min(int(page or 1), pages))
        return {'rows': rows[(page - 1) * per_page: page * per_page], 'page': page, 'pages': pages,
                'total': len(rows), 'per_page': per_page, 'counts': counts, 'kind': kind}

    def session_messages(self, start, end=None):
        """Every checked message inside one study session, oldest first."""
        end = end or time.time() + 1
        msgs = [e for e in self._store.read_log() if 'result' in e and start <= e['t'] <= end]
        out = []
        for m in dedupe(msgs):
            out.append(dict(m, kind=kind_of(m['result'])))
        return out

    def insights(self):
        events = self._store.read_log()
        msgs = dedupe([e for e in events if 'result' in e])
        sess = self.sessions(100000)
        today = datetime.now().date()
        def day(t): return datetime.fromtimestamp(t).date()
        per_day = {}
        for s in sess:
            d = per_day.setdefault(day(s['start']), {'s': 0, 'n': 0, 'c': 0})
            d['s'] += s.get('seconds', 0); d['n'] += 1
        for m in msgs:
            per_day.setdefault(day(m['t']), {'s': 0, 'n': 0, 'c': 0})['c'] += 1
        # calendar grid: whole weeks (Sunday first), ending with the current week
        start = today - timedelta(days=(today.weekday() + 1) % 7 + 7 * 17)
        heat = []
        d = start
        while d <= today:
            v = per_day.get(d, {'s': 0, 'n': 0, 'c': 0})
            heat.append({'d': d.isoformat(), 's': v['s'], 'n': v['n'], 'c': v['c'], 'dow': (d.weekday() + 1) % 7})
            d += timedelta(days=1)
        active = sorted(k for k, v in per_day.items() if v['n'] > 0)
        aset = set(active)
        cur, probe = 0, today if today in aset else today - timedelta(days=1)
        while probe in aset:
            cur += 1; probe -= timedelta(days=1)
        longest = run = 0
        prev = None
        for k in active:
            run = run + 1 if prev and (k - prev).days == 1 else 1
            longest = max(longest, run); prev = k
        t = tally(msgs)
        total = sum(t.values())
        by_site, by_class = {}, {}
        for m in msgs:
            by_site[site_name(m.get('where'))] = by_site.get(site_name(m.get('where')), 0) + 1
        classes_cfg = {c['name']: c.get('color') for c in self._store.data['classes']}
        for s in sess:                                   # time spent per class
            c = by_class.setdefault(s.get('class') or 'Other', {'seconds': 0, 'sessions': 0})
            c['seconds'] += s.get('seconds', 0); c['sessions'] += 1
        last7 = []
        for i in range(6, -1, -1):
            dd = today - timedelta(days=i)
            todays = [m for m in msgs if day(m['t']) == dd]
            tt = tally(todays)
            last7.append({'d': dd.isoformat(), 'label': dd.strftime('%a'), 'total': len(todays),
                          'bad': tt['flagged'] + tt['overridden']})
        run_now = best_run = 0
        for m in msgs:
            if kind_of(m['result']) in ('flagged', 'overridden'):
                run_now = 0
            else:
                run_now += 1; best_run = max(best_run, run_now)
        ai_ms = [m['ms'] for m in msgs if m.get('source') == 'ai' and m.get('ms')]
        secs = [s.get('seconds', 0) for s in sess]
        return {
            'totals': dict(t, total=total, sessions=len(sess), seconds=sum(secs),
                           longest_session=max(secs) if secs else 0,
                           avg_session=int(sum(secs) / len(secs)) if secs else 0,
                           avg_ms=int(sum(ai_ms) / len(ai_ms)) if ai_ms else 0),
            'clean_rate': round(100 * t['clean'] / total) if total else 100,
            'streak': {'current': cur, 'longest': longest, 'today_done': today in aset},
            'clean_run': {'current': run_now, 'best': best_run},
            'heat': heat,
            'sites': sorted(({'name': k, 'n': v} for k, v in by_site.items()), key=lambda x: -x['n'])[:6],
            'classes': sorted(({'name': k, 'color': 'ink' if k == 'Tutor mode' else (classes_cfg.get(k) or 'lav'), **v}
                               for k, v in by_class.items()), key=lambda x: -x['seconds'])[:6],
            'last7': last7,
        }

    def export_log(self):
        import webview
        kind = webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG
        dest = self._app.window.create_file_dialog(kind, save_filename='AI Integrity Report.txt')
        if not dest:
            return None
        dest = dest[0] if isinstance(dest, (list, tuple)) else dest
        entries = self._store.read_log()
        msgs = [e for e in entries if 'result' in e]
        t = tally(msgs)
        lines = ['AI Integrity Guard report', f'Generated {datetime.now():%b %d %Y %I:%M %p}',
                 f'{sum(1 for e in entries if e.get("event") == "session start")} study sessions, '
                 f'{len(msgs)} AI messages: {t["clean"]} clean, {t["flagged"]} flagged (held), '
                 f'{t["overridden"]} overridden (sent despite a warning)', '']
        for e in entries:
            when = datetime.fromtimestamp(e['t']).strftime('%b %d %I:%M %p')
            if 'event' in e:
                lines.append(f'[{when}] --- {e["event"]}: {e.get("class", "")} {e.get("assignment", "")}')
            else:
                lines.append(f'[{when}] {e["where"]} | {e["class"]} {e.get("assignment", "")} | {RESULT_LABEL.get(e["result"], e["result"].upper())}')
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
    def setup_ai(self):
        """Download (if needed) and load the built-in AI. Safe to call again to retry."""
        self._app.ai_guard.forget()
        self._app.engine.start()
        return self.state()

    def request_accessibility(self):
        watcher.has_accessibility(prompt=True)         # shows macOS's own permission prompt the first time
        watcher.open_accessibility_settings()
        return True

    def test_notification(self):
        watcher.notify('HonestHands', 'This is how a warning from your guard will look.')
        return True

    def open_notification_settings(self):
        import subprocess
        subprocess.Popen(['open', 'x-apple.systempreferences:com.apple.Notifications-Settings.extension'])
        return True

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

    # ---------- community (cloud) ----------
    def _cloud(self, fn, *a):
        try:
            return fn(*a)
        except cloudlib.CloudError as e:
            return _err(e)
        except Exception as e:
            return _err(f'Something went wrong: {e}')

    def cloud_status(self):
        c = self._app.cloud
        if not c.signed_in:
            return {'signed_in': False}
        r = self._cloud(c.me)
        if isinstance(r, dict) and r.get('error'):
            return {'signed_in': c.signed_in, 'error': r['error'], 'email': c.c.get('email')}
        return dict(r, signed_in=True, sync=c.status)

    def cloud_send_code(self, email):
        return self._cloud(self._app.cloud.send_code, email)

    def cloud_verify(self, email, code):
        return self._cloud(self._app.cloud.verify, email, code)

    def cloud_sign_up(self, email, password):
        return self._cloud(self._app.cloud.sign_up, email, password)

    def cloud_sign_in(self, email, password):
        return self._cloud(self._app.cloud.sign_in, email, password)

    def cloud_sign_out(self):
        self._app.cloud.sign_out()
        return True

    def cloud_set_profile(self, handle, name):
        return self._cloud(self._app.cloud.set_profile, handle, name)

    def cloud_set_sharing(self, on):
        return self._cloud(self._app.cloud.set_sharing, on)

    def cloud_overview(self):
        return self._cloud(self._app.cloud.overview)

    def cloud_invite(self, handle, mode):
        return self._cloud(self._app.cloud.invite, handle, mode)

    def cloud_respond(self, pid, accept):
        return self._cloud(self._app.cloud.respond, pid, accept)

    def cloud_end(self, pid):
        return self._cloud(self._app.cloud.end, pid)

    def cloud_friend(self, user_id):
        return self._cloud(self._app.cloud.friend, user_id)

    def cloud_conversations(self):
        return self._cloud(self._app.cloud.conversations)

    def cloud_thread(self, user_id):
        return self._cloud(self._app.cloud.thread, user_id)

    def cloud_send_message(self, user_id, body):
        return self._cloud(self._app.cloud.send_message, user_id, body)

    def cloud_releasers(self):
        return self._cloud(self._app.cloud.releasers)

    def cloud_request_unlock(self, note, watcher_ids):
        c, _ = self._store.session_targets()
        s = self._store.data.get('session') or {}
        left = max(0, int((s.get('ends_at', 0) - time.time()) / 60)) if s.get('ends_at') else 0
        return self._cloud(self._app.cloud.request_unlock, note, watcher_ids or None, c['name'] if c else '', left)

    def cloud_unlock_status(self):
        s = self._store.data.get('session') or {}
        return self._cloud(self._app.cloud.unlock_status, s.get('started') or time.time())

    def cloud_cancel_unlock(self, rid):
        return self._cloud(self._app.cloud.cancel_unlock, rid)

    def cloud_incoming_unlocks(self):
        return self._cloud(self._app.cloud.incoming_unlocks)

    def cloud_decide_unlock(self, rid, approve):
        return self._cloud(self._app.cloud.decide_unlock, rid, bool(approve))

    def cloud_sync_now(self):
        self._app.cloud.kick()
        return True

    def open_accessibility_settings(self):
        watcher.has_accessibility(prompt=True)
        watcher.open_accessibility_settings()
        return True

    def open_data_folder(self):
        subprocess.Popen(['open', str(APP_DIR)])
        return True
