"""Windows version of watcher.py (which reads other apps through macOS Accessibility).

winmain.py registers this module as `watcher` before anything else loads, so the shared code (bridge, cloud, extension_host...)
keeps working unchanged. Websites are guarded by the browser extension; desktop AI apps (ChatGPT, Claude...) are watched here: a keyboard hook
holds Enter, the text is read with Windows UI Automation, and the guard decides before the Enter goes through."""
import ctypes
import ctypes.wintypes as wt
import os
import re
import subprocess
import threading
import time

import rules

AI_APP_KEYWORDS = ['claude', 'chatgpt', 'openai', 'gemini', 'perplexity', 'copilot', 'deepseek',
                   'grok', 'mistral', 'poe', 'qwen', 'kimi', 'quillbot']
# On Windows a browser is identified by its program name, not a Mac bundle id.
BROWSERS = {'chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe', 'vivaldi.exe', 'arc.exe'}

_toast = None            # set by winmain: shows a tray balloon / toast


def set_toaster(fn):
    global _toast
    _toast = fn


def notify(title, message, action=''):
    if _toast:
        try:
            _toast(title, message, action)
            return
        except Exception:
            pass
    print(f'[notify] {title}: {message}', flush=True)


def has_accessibility(prompt=False):
    return True              # Windows needs no permission to see other windows


def open_accessibility_settings():
    pass


def is_ai_app(bid, name):
    if (bid or '').lower() in BROWSERS:
        return False
    hay = f'{bid} {name}'.lower()
    return any(k in hay for k in AI_APP_KEYWORDS)


class HHPanel:
    @staticmethod
    def show(*a, **k):
        pass



def diag(msg):
    """Tiny always-on log of what the typing watcher did (guard.log in the data folder), for when Enter seems stuck."""
    try:
        from store import APP_DIR
        f = APP_DIR / 'guard.log'
        if f.exists() and f.stat().st_size > 100_000:
            f.write_text(f.read_text()[-40_000:])
        with open(f, 'a') as fh:
            fh.write(time.strftime('%H:%M:%S ') + msg + '\n')
    except Exception:
        pass


# ------------------------------------------------------------------ Windows plumbing
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x201, 0x202
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x2, 0x4
SEND_WORDS = re.compile(r'\b(send|submit|run|generate)\b', re.I)     # narrow on purpose: 'message', 'go', 'ask' match unrelated buttons
SEND_GLYPHS = ('\u2191', '\u2197', '\u27a4', '\u2b06', '\u279c', '\u25b6', '\u21e7', '\u2b95')
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
VK_RETURN, VK_SHIFT, VK_MENU, VK_CONTROL = 0x0D, 0x10, 0x12, 0x11
KEYEVENTF_KEYUP = 0x2
INPUT_KEYBOARD, INPUT_MOUSE = 1, 0
CLICK_LOOKUP_WAIT = 0.25      # seconds allowed to look at a clicked button before letting the click through
WAIT_FOR_AI = 12          # seconds to wait for the AI before using the keyword rules
MARK = 0x48414E44            # tags the Enter we send ourselves, so the hook lets it through
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wt.DWORD), ('scanCode', wt.DWORD), ('flags', wt.DWORD), ('time', wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('pt', POINT), ('mouseData', wt.DWORD), ('flags', wt.DWORD), ('time', wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', wt.DWORD), ('dwFlags', wt.DWORD), ('time', wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wt.WORD), ('wScan', wt.WORD), ('dwFlags', wt.DWORD), ('time', wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('pad', ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [('type', wt.DWORD), ('u', _INPUTUNION)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.IsWindow.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.GetWindowThreadProcessId.restype = wt.DWORD


def exe_of(pid):
    """The program name (like 'chrome.exe') for a process id, or ''."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    exe = ''
    if h:
        buf = ctypes.create_unicode_buffer(520)
        n = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            exe = os.path.basename(buf.value).lower()
        kernel32.CloseHandle(h)
    return exe


def front_window():
    """(hwnd, program name like 'claude.exe', window title, pid) of whatever is in front."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, '', '', 0
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ''
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if h:
        buf = ctypes.create_unicode_buffer(520)
        n = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            exe = os.path.basename(buf.value).lower()
        kernel32.CloseHandle(h)
    title = ctypes.create_unicode_buffer(300)
    user32.GetWindowTextW(hwnd, title, 300)
    return hwnd, exe, title.value, pid.value


def ai_app_name(exe, title):
    """'Claude app' etc. if this is a desktop AI app (not a browser), else None."""
    if exe in BROWSERS:
        return None
    hay = f'{exe} {title}'.lower()
    for k in AI_APP_KEYWORDS:
        if k in hay:
            return k.capitalize() + ' app'
    return None


def send_enter():
    """Press Enter for the person (after the guard said yes). Tagged so our own hook does not catch it again."""
    down, up = INPUT(), INPUT()
    down.type = up.type = INPUT_KEYBOARD
    down.u.ki = KEYBDINPUT(VK_RETURN, 0, 0, 0, MARK)
    up.u.ki = KEYBDINPUT(VK_RETURN, 0, KEYEVENTF_KEYUP, 0, MARK)
    arr = (INPUT * 2)(down, up)
    user32.SendInput(2, arr, ctypes.sizeof(INPUT))


def send_click(x, y):
    """Click at a screen point for the person (after the guard said yes). Tagged so our own hook lets it through."""
    user32.SetCursorPos(int(x), int(y))
    down, up = INPUT(), INPUT()
    down.type = up.type = INPUT_MOUSE
    down.u.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, MARK)
    up.u.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, MARK)
    arr = (INPUT * 2)(down, up)
    user32.SendInput(2, arr, ctypes.sizeof(INPUT))


class _ClickLookup:
    """One long-lived thread with UI Automation already started, so looking at a clicked button takes milliseconds instead of
    the first-call delay (which would make the first clicks slip past unchecked)."""

    def __init__(self):
        import queue
        self._q = queue.Queue()
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread():
                try:
                    auto.ControlFromPoint(1, 1)                  # warm-up: the slow first call happens now, not on a click
                except Exception:
                    pass
                self._ready.set()
                while True:
                    x, y, box, done = self._q.get()
                    try:
                        box['send'] = _control_is_send(auto, x, y)
                    except Exception as e:
                        box['send'] = None
                        print('[guard] click lookup failed:', e, flush=True)
                    done.set()
        except Exception as e:
            print('[guard] click lookup thread could not start:', e, flush=True)
            self._ready.set()

    def is_send(self, x, y, wait):
        if not self._ready.is_set():
            return None                                          # still warming up: do not hold clicks yet
        box, done = {}, threading.Event()
        self._q.put((x, y, box, done))
        done.wait(wait)
        return box.get('send')


_LOOKUP = None


def _control_is_send(auto, x, y):
    c = auto.ControlFromPoint(int(x), int(y))
    for _ in range(3):                                           # the click can land on an icon inside the button
        if c is None:
            return False
        label = ' '.join(str(v or '') for v in (c.Name, c.AutomationId, c.HelpText))
        if SEND_WORDS.search(label) or any(g in label for g in SEND_GLYPHS):
            return True
        if c.ControlTypeName == 'ButtonControl':
            return False
        c = c.GetParentControl()
    return False


def click_is_send(x, y):
    """Is the control under this point a 'send' button? Looks at its name / id through UI Automation."""
    try:
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            c = auto.ControlFromPoint(int(x), int(y))
            for _ in range(3):                                   # the click can land on an icon inside the button
                if c is None:
                    return False
                label = ' '.join(str(v or '') for v in (c.Name, c.AutomationId, c.HelpText))
                if SEND_WORDS.search(label) or any(g in label for g in SEND_GLYPHS):
                    return True
                if c.ControlTypeName == 'ButtonControl':
                    return False
                c = c.GetParentControl()
    except Exception as e:
        print('[guard] could not look at the clicked control:', e, flush=True)
    return False


def read_focused_text():
    """The text in whatever box has the keyboard focus, through UI Automation. '' if it can't be read."""
    try:
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            c = auto.GetFocusedControl()
            if c is None:
                return ''
            text = ''
            try:
                text = c.GetValuePattern().Value or ''
            except Exception:
                pass
            if not text:
                try:
                    text = c.GetTextPattern().DocumentRange.GetText(-1) or ''
                except Exception:
                    pass
            return (text or '').strip()
    except Exception as e:
        print('[guard] could not read the text box:', e, flush=True)
        return ''


class Guard:
    """Holds Enter in desktop AI apps until the text has been checked. The same decisions as the Mac guard: allow, or show
    the warning (Edit / Send anyway) and log the outcome."""
    overlay_hook = None
    block_handler = None
    on_override = None

    def __init__(self, store, ai_guard):
        self.store, self.ai_guard = store, ai_guard
        self.watching = False
        self.locked = False
        self.sent_anyway = None
        self._t_start = 0.0
        self._swallowed_up = False
        self._hook = None
        self._proc = None
        self._mhook = None
        self._mproc = None
        self._swallow_click_up = False

    # ---------------------------------------------------------------- the keyboard hook
    def install(self):
        global _LOOKUP
        if self._hook is not None:
            return True
        if _LOOKUP is None:
            _LOOKUP = _ClickLookup()
        ready = threading.Event()

        def run():
            self._proc = HOOKPROC(self._on_key)
            self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
            self._mproc = HOOKPROC(self._on_mouse)
            self._mhook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mproc, None, 0)
            self.watching = bool(self._hook)
            ready.set()
            if not self._hook:
                return
            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:      # a hook thread must pump messages
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        threading.Thread(target=run, daemon=True).start()
        ready.wait(3)
        return self.watching

    def start_typing_watch(self):
        pass

    def _on_key(self, nCode, wParam, lParam):
        try:
            if nCode == 0:
                k = KBDLLHOOKSTRUCT.from_address(lParam)
                if k.vkCode == VK_RETURN and k.dwExtraInfo != MARK:
                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        if self._enter_down():
                            self._swallowed_up = True
                            return 1                          # held: the app never sees this Enter
                    elif wParam in (WM_KEYUP, WM_SYSKEYUP) and self._swallowed_up:
                        self._swallowed_up = False
                        return 1
        except Exception as e:                                # never freeze the keyboard over a bug
            print('[guard] hook error, letting it through:', e, flush=True)
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _on_mouse(self, nCode, wParam, lParam):
        try:
            if nCode == 0:
                m = MSLLHOOKSTRUCT.from_address(lParam)
                if m.dwExtraInfo != MARK:
                    if wParam == WM_LBUTTONDOWN:
                        if self._click_down(m.pt.x, m.pt.y):
                            self._swallow_click_up = True
                            return 1
                    elif wParam == WM_LBUTTONUP and self._swallow_click_up:
                        self._swallow_click_up = False
                        return 1
        except Exception as e:
            print('[guard] mouse hook error, letting it through:', e, flush=True)
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _click_down(self, x, y):
        """A click on a Send button in a desktop AI app is held like Enter is. Looking at the button is quick but not instant, so
        only wait a moment: if Windows is slow to answer, the click goes through untouched."""
        cls, asg = self.store.session_targets()
        if not cls or self.locked:
            return False
        hwnd, exe, title, pid = front_window()
        where = ai_app_name(exe, title)
        if not where:
            return False
        t0 = time.time()
        is_send = _LOOKUP.is_send(x, y, CLICK_LOOKUP_WAIT) if _LOOKUP is not None else None
        diag(f'click at ({x},{y}) in {exe!r}: send button? {is_send} (looked for {int((time.time() - t0) * 1000)} ms)')
        if not is_send:
            return False
        diag(f'Send click in {exe!r} -> watching as {where}')
        self.locked = True
        self._t_start = time.time()
        threading.Thread(target=self._decide, args=(hwnd, pid, where, cls, asg, 'click', (x, y)), daemon=True).start()
        return True

    def _resend(self, trigger, loc):
        if trigger == 'click' and loc:
            send_click(*loc)
        else:
            send_enter()

    def _enter_down(self):
        cls, asg = self.store.session_targets()
        if not cls:
            return False
        if user32.GetAsyncKeyState(VK_SHIFT) & 0x8000 or user32.GetAsyncKeyState(VK_MENU) & 0x8000 or user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
            return False                                      # Shift/Alt/Ctrl+Enter is a new line, not a send
        hwnd, exe, title, pid = front_window()
        where = ai_app_name(exe, title)
        diag(f'Enter in {exe!r} / {title[:40]!r} -> ' + (f'watching as {where}' if where else 'not an AI app, let through'))
        if not where:
            return False
        if self.locked and time.time() - self._t_start > 15 and not (Guard.overlay_hook is not None and Guard.overlay_hook.is_open()):
            self.locked = False                               # a stale hold must never leave Enter dead
        if self.locked:
            return True                                       # a check or a warning is already in progress
        self.locked = True
        self._t_start = time.time()
        threading.Thread(target=self._decide, args=(hwnd, pid, where, cls, asg, 'enter', None), daemon=True).start()
        return True

    # ---------------------------------------------------------------- the decision
    def _decide(self, hwnd, pid, where, cls, asg, trigger='enter', loc=None):
        try:
            text = read_focused_text()
            diag(f'read text: {text[:50]!r}')
            if not text:
                self._release(); self._resend(trigger, loc); return   # nothing to check (or unreadable): let it through
            p = {'pid': pid, 'hwnd': hwnd, 'where': where, 'text': text, 'trigger': trigger, 'loc': loc}
            sa = self.sent_anyway
            if sa and sa[0].strip() == text and time.time() < sa[1]:
                self._release(); self._resend(trigger, loc); return
            r = self.ai_guard.cached(text, cls, asg)
            diag(f'cached: {r is not None}; engine ready: {self.ai_guard.engine.ready()}')
            if r is None and (rules.check(text, cls, asg).get('evade') or not self.ai_guard.engine.ready()):
                r = self.ai_guard.check(text, cls, asg, where)
                diag('instant check done')
            if r is None:
                hook = Guard.overlay_hook
                if hook is not None:
                    try:
                        hook.checking()
                    except Exception:
                        pass
                # A slow computer can take a long time to run the AI. Wait a few seconds, then fall back to the keyword rules
                # so Enter is never held for long (the AI result, if it finishes later, is cached for next time).
                box = {}

                def run_check():
                    try:
                        box['r'] = self.ai_guard.check(text, cls, asg, where, timeout=10)
                    except Exception as e:
                        box['err'] = e
                t = threading.Thread(target=run_check, daemon=True)
                t.start()
                t.join(WAIT_FOR_AI)
                r = box.get('r')
                if r is None:
                    why = box.get('err') or 'the AI was slow'
                    diag(f'AI check fallback: {why}')
                    r = dict(rules.check(text, cls, asg), source='keywords', note=str(why))
                    r['verdict'] = 'allow' if r['level'] != 'flag' else 'warn'
            diag(f'verdict: level={r.get("level")} source={r.get("source")}')
            self._finish(r, p, cls, asg)
        except Exception as e:
            diag(f'decision error, letting it through: {e!r}')
            print('[guard] decision error, letting it through:', e, flush=True)
            self._release()
            self._resend(trigger, loc)

    def _finish(self, r, p, cls, asg):
        if r['level'] in ('ok', 'note'):
            hook = Guard.overlay_hook
            if hook is not None:
                try:
                    hook.ok()
                except Exception:
                    pass
            self.record(p, cls, asg, p.get('trigger', 'enter'), 'ok (disclose)' if r['level'] == 'note' else 'ok', r)
            if r['level'] == 'note' and r.get('reasons'):
                notify('HonestHands', r['reasons'][0])
            same = front_window()[0] == p['hwnd']
            self._release()
            if same:
                self._resend(p.get('trigger'), p.get('loc'))
            else:
                notify('HonestHands', "Your message passed the check but wasn't sent because you switched apps. Send it again.")
            return
        hard = self.is_hard(r)
        self.record(p, cls, asg, p.get('trigger', 'enter'), 'blocked' if hard else 'warned', r)
        self.show_warning(r, hard, p, cls, asg)               # stays held until the person chooses

    def show_warning(self, r, hard, p, cls, asg):
        try:
            if Guard.block_handler is not None:
                Guard.block_handler(self, r, hard, p, cls, asg)
                return
        except Exception as e:
            print('[guard] warning handler error, releasing:', e, flush=True)
        self._release()

    def on_panel_choice(self, choice, p):
        ev = p.get('event')
        if ev is not None:                                    # browser-extension path: hand the answer back
            p['choice'] = choice
            ev.set()
            return
        if choice == 'send_anyway':
            cls, asg = self.store.session_targets()
            if cls:
                self.record(p, cls, asg, 'overlay', 'sent anyway', None)
                self.sent_anyway = (p.get('text', ''), time.time() + 20)
            same = front_window()[0] == p.get('hwnd')
            self._release()
            if same:
                threading.Timer(0.35, lambda: self._resend(p.get('trigger'), p.get('loc'))).start()
            return
        self._release()

    def record(self, p, cls, asg, trigger, result, r):
        entry = {'t': time.time(), 'where': p['where'], 'class': cls['name'], 'assignment': asg['name'] if asg else '',
                 'trigger': trigger, 'text': p['text'][:300], 'result': result}
        if r:
            entry['source'] = r.get('source')
            entry['ms'] = r.get('ms')
            if r.get('note'):
                entry['note'] = r['note']
            if r.get('level') == 'flag':
                entry['reasons'] = r.get('reasons')
        self.store.log(entry)
        if result in ('sent anyway', 'sent after warning') and Guard.on_override:
            try:
                Guard.on_override()
            except Exception:
                pass

    def is_hard(self, r):
        return bool(r.get('hard'))

    def _release(self):
        self.locked = False
