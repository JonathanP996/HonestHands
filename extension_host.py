"""The browser extension's side of the app: it asks "is this message OK?" and waits for the answer.
Shared by the Mac app (main.py) and the Windows app (winmain.py). The host provides: store, ai_guard, guard, cloud,
native_overlay, show_overlay_block(...) and _main(fn, *args) (run something on the UI thread)."""
import time

import slowai
import watcher


class ExtensionHost:
    _ext_last_ping = 0.0

    def note_extension_ping(self, browser=''):
        import time as _t
        self._ext_last_ping = _t.time()
        if browser:
            self._ext_pings[browser] = self._ext_last_ping

    def extension_seen_recently(self, browser=None):
        """Has the extension checked in lately? (Within 90s, which tolerates the browser putting its worker to sleep.)
        With a guarded browser chosen, only THAT browser's extension counts."""
        import time as _t
        chosen = browser or self.store.data.get('browser')
        if chosen:
            return (_t.time() - self._ext_pings.get(chosen, 0)) < 90
        return (_t.time() - self._ext_last_ping) < 90

    def extension_active(self):
        '''The extension acts ONLY when the app is running AND a session is on.'''
        try:
            cls, _ = self.store.session_targets()
            return cls is not None
        except Exception:
            return False

    def extension_check(self, text, site, url, images=None, n_images=0):
        '''Check a message the extension intercepted. Returns a verdict dict and logs it.
        Mirrors the Accessibility path so rules/log stay unified.'''
        cls, asg = self.store.session_targets()
        if cls is None:
            return {'verdict': 'allow'}
        text = (text or '').strip()
        images = [i for i in (images or []) if isinstance(i, str)][:3]
        has_pic = bool(images) or n_images > 0
        if not text and not has_pic:
            return {'verdict': 'allow'}
        where = site or 'browser'
        hook = getattr(self, 'native_overlay', None)
        if hook is not None and (has_pic or not self.ai_guard.cached(text, cls, asg)):
            self._main(hook.checking)
        sa = getattr(self.guard, 'sent_anyway', None)
        if sa and sa[0].strip() == text and time.time() < sa[1]:
            return {'verdict': 'allow'}
        if has_pic:
            r = slowai.check_with_fallback(self.ai_guard, lambda: self.ai_guard.check_with_images(text, images, cls, asg, where, timeout=slowai.WAIT, n_images=n_images), text, cls, asg)
            text = (text + ' ' if text else '') + f'[+{max(len(images), n_images)} picture{"s" if max(len(images), n_images) != 1 else ""}]'
        else:
            r = slowai.check_with_fallback(self.ai_guard, lambda: self.ai_guard.check(text, cls, asg, where, timeout=slowai.WAIT), text, cls, asg)
        # Map to the extension's simple contract + details for the warning panel.
        verdict = r.get('verdict', 'allow')
        hard = self.guard.is_hard(r) if r.get('level') == 'flag' else False
        # Log it the same way the Accessibility guard does.
        entry = {'t': __import__('time').time(), 'where': where, 'class': cls['name'],
                 'assignment': asg['name'] if asg else '', 'trigger': 'extension',
                 'text': text[:300],
                 'result': ('blocked' if hard else 'warned') if r.get('level') == 'flag'
                           else ('ok (disclose)' if r.get('level') == 'note' else 'ok'),
                 'source': r.get('source'), 'ms': r.get('ms')}
        if r.get('level') == 'flag':
            entry['reasons'] = r.get('reasons')
        self.store.log(entry)
        # If flagged, show the native warning panel (same as Accessibility path).
        if r.get('level') == 'flag':
            import threading as _th
            p = {'pid': 0, 'where': where, 'text': text, 'event': _th.Event(), 'choice': 'edit'}
            self._main(self.show_overlay_block if getattr(self, 'native_overlay', None) else watcher.HHPanel.show,
                       self.guard, r, hard, p, cls, asg)
            # Wait for the user's button press: "Send it now" lets the page send; anything else holds it.
            p['event'].wait(timeout=120)
            if p['choice'] == 'send_anyway' and not hard:
                self.store.log({'t': __import__('time').time(), 'where': where, 'class': cls['name'],
                                'assignment': asg['name'] if asg else '', 'trigger': 'extension',
                                'text': text[:300], 'result': 'sent anyway'})
                self.cloud.kick()
                return {'verdict': 'allow', 'sent_anyway': True}
            return {'verdict': 'block' if hard else 'warn',
                    'reason': r.get('reason', ''), 'rule': r.get('rule', ''),
                    'quote': r.get('quote', ''), 'tip': r.get('tip', ''), 'hard': hard}
        if hook is not None:
            self._main(hook.ok)
        return {'verdict': 'allow'}
