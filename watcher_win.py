"""Windows stand-in for watcher.py (which reads other apps through macOS Accessibility).

winmain.py registers this module as `watcher` before anything else loads, so the shared code (bridge, cloud, extension_host...)
keeps working unchanged. For now the Windows guard works through the browser extension; watching desktop apps comes later."""
import re
import subprocess
import threading
import time

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


class Guard:
    """Holds what the Mac guard holds for the shared code: flags the app reads and the choice handler. The part that watches
    other apps' text boxes is not built yet (that is the next piece of Windows work)."""
    overlay_hook = None
    block_handler = None
    on_override = None

    def __init__(self, store, ai_guard):
        self.store, self.ai_guard = store, ai_guard
        self.watching = False
        self.locked = False
        self.sent_anyway = None

    def install(self):
        return True

    def start_typing_watch(self):
        pass

    def is_hard(self, r):
        return bool(r.get('hard'))

    def _release(self):
        self.locked = False

    def on_panel_choice(self, choice, p):
        ev = p.get('event')
        if ev is not None:                       # browser-extension path: hand the answer back
            p['choice'] = choice
            ev.set()
            return
        self._release()
