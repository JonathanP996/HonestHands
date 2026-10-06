"""The warning popup on Windows: a small borderless, always-on-top web window (ui/overlay.html) at the bottom of the screen.
Same interface as the Mac's native popup (overlay_client): show(payload, on_choice), checking(), ok(), hide(), is_open()."""
import json
import threading

import webview


class _Api:
    def __init__(self, owner):
        self._o = owner

    def choose(self, choice):
        return self._o._chosen(choice)


class WinOverlay:
    def __init__(self, resource):
        self._cb = None
        self._open = False
        self.window = webview.create_window('HonestHands Overlay', url=resource('ui', 'overlay.html'), js_api=_Api(self),
                                            frameless=True, on_top=True, hidden=True, width=520, height=340,
                                            transparent=True, resizable=False, easy_drag=False)

    # --- the popup interface the shared code expects
    def is_open(self):
        return self._open

    def owns_point(self, x, y):
        return False

    def show(self, payload, on_choice):
        mapped = {'hard': payload.get('hard'), 'reason': payload.get('reason', ''), 'rule': payload.get('rule', ''),
                  'quote': payload.get('quote', ''), 'tip': payload.get('tip', ''), 'where': payload.get('context', ''),
                  'source': payload.get('source', ''), 'class': '', 'assignment': ''}
        self._cb = on_choice
        self._open = True
        try:
            self._place()
            self.window.show()
            self.window.evaluate_js('showBlock(' + json.dumps(mapped) + ')')
            return True
        except Exception as e:
            print('overlay show failed:', e, flush=True)
            self._open = False
            return False

    def checking(self):
        pass                                     # the Windows popup has no "checking" state yet

    def ok(self):
        pass

    def hide(self):
        self._open = False
        try:
            self.window.hide()
        except Exception:
            pass

    def _place(self):
        try:
            import ctypes
            w, h = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
            self.window.move((w - 520) // 2, h - 340 - 90)
        except Exception:
            pass

    def _chosen(self, choice):
        cb, self._cb = self._cb, None
        self.hide()
        if cb:
            threading.Thread(target=cb, args=(choice,), daemon=True).start()
        return True
