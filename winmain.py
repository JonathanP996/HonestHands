"""HonestHands for Windows: the same screens, AI guard, accounts and extension bridge as the Mac app, with a tray icon.

Run:  python winmain.py
The Mac-only watcher is replaced by watcher_win (see WINDOWS.md); everything else is the shared code."""
import os
import sys

if len(sys.argv) > 1 and sys.argv[1] == '--watchdog':
    raise SystemExit('The lock-in watcher is not built for Windows yet.')

import watcher_win                      # must come first: the shared code does `import watcher`
sys.modules['watcher'] = watcher_win

import socket
import threading
import time

import webview

import bridge_server
import cloud
import extension_host
import updates
import winoverlay
from ai_guard import AIGuard
from bridge import Api
from engine import Engine
from store import APP_DIR, Store

SINGLE_PORT = 7674


def resource(*parts):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def ensure_single_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', SINGLE_PORT))
    except OSError:
        return False
    ensure_single_instance._s = s
    return True


class WinApp(extension_host.ExtensionHost):
    _main = staticmethod(lambda fn, *a, **k: threading.Thread(target=fn, args=a, kwargs=k, daemon=True).start())

    def __init__(self):
        self.store = Store()
        self.engine = Engine(self.store)
        self.ai_guard = AIGuard(self.store, self.engine)
        self.guard = watcher_win.Guard(self.store, self.ai_guard)
        self.api = None
        self.cloud = cloud.Cloud(self.store, self)
        self.updater = updates.Updater(self.store, self._update_found)
        self.api = Api(self)
        self.cloud.app = self
        self.window = None
        self.native_overlay = None
        self.tray = None
        self.quitting = False
        self._ext_last_ping = 0.0
        self._ext_pings = {}
        watcher_win.Guard.on_override = self.cloud.kick

    # ---- timed lock-in (the shared rules; the "hide other apps" part comes later)
    def locked_now(self):
        s = self.store.data.get('session') or {}
        return bool(s.get('locked') and s.get('ends_at', 0) > time.time())

    def release_session(self, why):
        self.api._finish_session(why, ended_by=why)

    def _lock_tick(self):
        while True:
            time.sleep(2)
            try:
                self.api.finish_if_due()
            except Exception as e:
                print('[lock] tick problem:', e, flush=True)

    def _lock_message(self, reason, app_name):
        watcher_win.notify('HonestHands', reason)

    def _update_found(self, latest):
        watcher_win.notify('HonestHands', 'A new version is ready. Open HonestHands to update.', 'home')

    def refresh_menu(self):
        pass

    def resolve_block(self, choice):
        return True

    # ---- warning popup
    def show_overlay_block(self, guard, r, hard, p, cls, asg):
        native = self.native_overlay
        if native is None:
            guard._release()
            return
        reason = r.get('reason') or (r.get('reasons') or ['This looks like it breaks a rule for this class.'])[0]
        payload = {'hard': bool(hard), 'title': 'Message blocked' if hard else 'Hold on a second',
                   'context': cls['name'] + (f' / {asg["name"]}' if asg else '') + ' · ' + p.get('where', ''),
                   'reason': reason, 'rule': r.get('rule', ''), 'quote': r.get('quote', ''), 'tip': r.get('tip', ''),
                   'source': 'AI guard' if r.get('source') == 'ai' else 'keyword rules', 'allowSend': not hard}
        on_choice = lambda choice: guard.on_panel_choice('send_anyway' if choice == 'send_anyway' else 'edit', p)
        if not native.show(payload, on_choice):
            guard._release()

    # ---- window + tray
    def show_window(self):
        if self.window:
            try:
                self.window.show()
                self.window.restore()
            except Exception:
                pass

    def _need_out(self):
        self.show_window()
        try:
            self.window.evaluate_js("typeof openNeedOut === 'function' && openNeedOut()")
        except Exception:
            pass

    def on_closing(self):
        if not self.quitting and self.locked_now():
            self.window.hide()                  # a lock-in keeps HonestHands running; closing just tucks the window away
            return False
        if not self.quitting and self.store.data.get('session') and self.store.data.get('pin'):
            self._need_out()
            return False
        self.quitting = True
        self._stop()
        return True

    def quit(self):
        if self.locked_now() or (self.store.data.get('session') and self.store.data.get('pin')):
            self._need_out()
            return
        self.quitting = True
        self._stop()
        try:
            self.window.destroy()
        except Exception:
            os._exit(0)

    def _stop(self):
        self.engine.stop_server()
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass

    def _start_tray(self):
        try:
            import pystray
            from PIL import Image
            img = Image.open(resource('extension', 'icon-128.png'))
            menu = pystray.Menu(pystray.MenuItem('Open HonestHands', lambda: self.show_window(), default=True),
                                pystray.MenuItem('Quit', lambda: self.quit()))
            self.tray = pystray.Icon('HonestHands', img, 'HonestHands', menu)
            self.tray.run_detached()
            watcher_win.set_toaster(lambda title, msg, action='': self.tray.notify(msg, title))
        except Exception as e:
            print('tray icon unavailable:', e, flush=True)

    def on_started(self):
        self._start_tray()
        self.engine.autostart()
        self.cloud.start()
        self.updater.start()
        threading.Thread(target=self._lock_tick, daemon=True).start()
        watcher_win.Guard.block_handler = self.show_overlay_block
        watcher_win.Guard.overlay_hook = self.native_overlay
        try:
            bridge_server.start(self)
        except Exception as e:
            print('extension server not started:', e, flush=True)

    def run(self):
        if not ensure_single_instance():
            return
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.window = webview.create_window('HonestHands', url=resource('ui', 'index.html'), js_api=self.api,
                                            width=1060, height=740, min_size=(860, 600))
        self.window.events.closing += self.on_closing
        self.native_overlay = winoverlay.WinOverlay(resource)
        try:
            webview.start(self.on_started)
        finally:
            self.engine.stop_server()


if __name__ == '__main__':
    WinApp().run()
