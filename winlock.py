"""Stay locked in, on Windows: while a study session is on, a blocked window that comes to the front is minimized and the
guarded browser (or wherever you were) is brought back, with a short note. The same rules as lock.py on the Mac:
other browsers are blocked once you have chosen one, AI desktop apps optionally, and any app on the custom list."""
import ctypes
import ctypes.wintypes as wt
import threading
import time

import watcher_win as W

SW_MINIMIZE, SW_RESTORE = 6, 9
from winlockrules import EXE_TO_KEY, blocked_reason, pretty


class SessionLock:
    def __init__(self, store, on_block, is_ai_app):
        self.store, self.on_block, self.is_ai_app = store, on_block, is_ai_app
        self.last_ok = None            # the last allowed window that was in front: where to put you back
        self.blocked = 0
        self._last_msg = {}
        self._started = False

    def active(self):
        cls, _ = self.store.session_targets()
        return cls is not None

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._watch, daemon=True).start()

    # ------------------------------------------------------------ windows
    @staticmethod
    def _windows():
        """Every visible top-level window: (hwnd, exe, title, minimized)."""
        user32 = W.user32
        out = []
        EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def cb(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                buf = ctypes.create_unicode_buffer(300)
                user32.GetWindowTextW(hwnd, buf, 300)
                if not buf.value:
                    return True
                pid = wt.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                exe = W.exe_of(pid.value)
                out.append((hwnd, exe, buf.value, bool(user32.IsIconic(hwnd))))
            except Exception:
                pass
            return True

        user32.EnumWindows(EnumProc(cb), 0)
        return out

    def _watch(self):
        user32 = W.user32
        while True:
            time.sleep(0.5)
            try:
                if not self.active():
                    continue
                cfg = self.store.data.get('lock') or {}
                chosen = self.store.data.get('browser') or ''
                front, fexe, ftitle, _ = W.front_window()
                for hwnd, exe, title, minimized in self._windows():
                    if exe == 'honesthands.exe' or exe.startswith('python'):
                        continue                                    # never block ourselves
                    reason = blocked_reason(exe, title, cfg, chosen, self.is_ai_app)
                    if reason is None:
                        if hwnd == front:
                            self.last_ok = hwnd
                        continue
                    if hwnd == front:
                        self._turn_back(hwnd, exe, reason)
                    elif not minimized:
                        user32.ShowWindow(hwnd, SW_MINIMIZE)        # open behind something else: still out of sight
            except Exception as e:
                print('[lock] check problem:', e, flush=True)

    def _turn_back(self, hwnd, exe, reason):
        user32 = W.user32
        self.blocked += 1
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        self._return_to_work()
        name = pretty(exe)
        if time.time() - self._last_msg.get(name, 0) > 4:            # repeated tries don't stack popups
            self._last_msg[name] = time.time()
            self.on_block(reason, name)

    def _return_to_work(self):
        """Bring the guarded browser (or wherever you were) back to the front."""
        user32 = W.user32
        chosen = self.store.data.get('browser') or ''
        want = [k for k, v in EXE_TO_KEY.items() if v == chosen]
        target = None
        if want:
            for hwnd, exe, title, minimized in self._windows():
                if exe in want:
                    target = hwnd
                    break
        if target is None and self.last_ok and user32.IsWindow(self.last_ok):
            target = self.last_ok
        if target:
            if user32.IsIconic(target):
                user32.ShowWindow(target, SW_RESTORE)
            self._foreground(target)

    @staticmethod
    def _foreground(hwnd):
        """Windows only lets the foreground program take focus, so borrow its input thread for a moment."""
        user32 = W.user32
        try:
            cur = user32.GetForegroundWindow()
            t1 = user32.GetWindowThreadProcessId(cur, None)
            t2 = W.kernel32.GetCurrentThreadId()
            user32.AttachThreadInput(t2, t1, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(t2, t1, False)
        except Exception:
            pass
