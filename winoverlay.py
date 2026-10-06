"""The warning popup on Windows: the same card as the Mac's native one (see ui/overlay_win.html), top-right, over everything.
It is a small borderless web window that never takes the keyboard focus (so the AI app you were typing in stays in front);
the keys Esc / Enter / Ctrl+Enter are handled by the keyboard watcher while the card is open.

Same interface as the Mac's overlay_client: show(payload, on_choice), checking(), ok(), hide(), is_open(), choose()."""
import ctypes
import ctypes.wintypes as wt
import json
import threading

import webview


def _log(msg):
    try:
        import watcher_win
        watcher_win.diag('overlay: ' + msg)
    except Exception:
        pass

TITLE = 'HonestHands Overlay'
WIDTH = 440
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x08000000, 0x00000080, 0x00000008
SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOMOVE = 0x10, 0x1, 0x2


class _Api:
    def __init__(self, owner):
        self._o = owner

    def choose(self, choice):
        return self._o._chosen(choice)

    def resize(self, height):
        return self._o._resize(height)

    def done(self):
        return self._o._finished()


class WinOverlay:
    def __init__(self, resource):
        self._cb = None
        self._open = False          # a warning card is showing (not just a pill)
        self._allow_send = False
        self._ready = False
        self._visible = False
        self._styled = False
        self._h = 120
        kw = dict(url=resource('ui', 'overlay_win.html'), js_api=_Api(self), frameless=True, on_top=True, hidden=True,
                  width=WIDTH, height=self._h, transparent=True, resizable=False, easy_drag=False)
        try:
            self.window = webview.create_window(TITLE, focus=False, **kw)
        except TypeError:
            self.window = webview.create_window(TITLE, **kw)
        try:
            self.window.events.loaded += lambda: setattr(self, '_ready', True)
        except Exception:
            self._ready = True

    # ------------------------------------------------------------ the popup interface the shared code expects
    def is_open(self):
        return self._open

    def owns_point(self, x, y):
        return False

    def show(self, payload, on_choice):
        self._cb = on_choice
        self._open = True
        self._allow_send = bool(payload.get('allowSend', not payload.get('hard')))
        return self._run('showBlock(' + json.dumps(payload) + ')')

    def checking(self):
        return self._run('showChecking()')

    def ok(self):
        return self._run('showOk()')

    def hide(self):
        self._open = False
        self._visible = False
        try:
            self.window.evaluate_js('hideAll()')
        except Exception:
            pass
        try:
            self.window.hide()
        except Exception:
            pass

    def choose(self, choice):
        """Called by the keyboard watcher when Esc / Enter / Ctrl+Enter is pressed while the card is open."""
        if choice == 'send_anyway' and not self._allow_send:
            choice = 'edit'
        try:
            self.window.evaluate_js("choose('%s')" % ('send_anyway' if choice == 'send_anyway' else 'edit'))
        except Exception:
            self._chosen(choice)
        return True

    # ------------------------------------------------------------ internals
    def _run(self, js):
        try:
            self._style_once()
            self._place(self._h)
            if not self._visible:
                self.window.show()
                self._visible = True
            self._wait_ready()
            self.window.evaluate_js(js)
            _log(f'{js.split("(")[0]} sent (ready={self._ready}, height={self._h})')
            return True
        except Exception as e:
            _log(f'show failed: {e!r}')
            print('overlay show failed:', e, flush=True)
            self._open = False
            return False

    def _wait_ready(self):
        import time
        for _ in range(60):
            if self._ready:
                return
            time.sleep(0.05)

    def _style_once(self):
        """Make the window a tool window that never takes focus and floats over everything."""
        if self._styled:
            return
        try:
            u = ctypes.WinDLL('user32', use_last_error=True)
            u.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
            u.FindWindowW.restype = wt.HWND
            u.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
            hwnd = u.FindWindowW(None, TITLE)
            if hwnd:
                u.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
                self._styled = True
        except Exception as e:
            _log(f'style note: {e!r}')
            print('overlay style note:', e, flush=True)

    def _place(self, height):
        try:
            u = ctypes.windll.user32
            w = u.GetSystemMetrics(0)
            self.window.resize(WIDTH, max(60, int(height)))
            self.window.move(w - WIDTH - 6, 36)
        except Exception:
            pass

    def _resize(self, height):
        self._h = max(60, min(int(height) + 8, 900))
        if self._visible:
            self._place(self._h)
        return True

    def _finished(self):
        """The 'you're good' pill has slid away."""
        if not self._open:
            self.hide()
        return True

    def _chosen(self, choice):
        cb, self._cb = self._cb, None
        self.hide()
        if cb:
            threading.Thread(target=cb, args=(choice,), daemon=True).start()
        return True
