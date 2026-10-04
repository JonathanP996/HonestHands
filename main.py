"""AI Integrity Guard: the Mac app."""
import os
import sys
import threading

import objc
import webview
from AppKit import (
    NSApplication,
    NSBezierPath,
    NSColor,
    NSImage,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject
from PyObjCTools import AppHelper

import watcher
import bridge_server
from bridge import Api
from store import APP_DIR


def ensure_single_instance():
    """Stop a second copy of HonestHands from launching (prevents any relaunch pile-up)."""
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    lock_path = str(APP_DIR / 'honesthands.lock')
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            s.bind('\0honesthands')      # abstract socket: auto-released when this process dies
        except OSError:
            # Fall back to a file lock for older systems.
            import fcntl
            f = open(lock_path, 'w')
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            ensure_single_instance._f = f
            return True
        ensure_single_instance._s = s
        return True
    except OSError:
        return False  # another instance holds the lock
from engine import Engine
from judge import Judge
from store import Store


def resource(*parts):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


class MenuTarget(NSObject):
    def initWithApp_(self, app):
        self = objc.super(MenuTarget, self).init()
        if self is None:
            return None
        self.app = app
        return self

    def openWindow_(self, sender):
        self.app.show_window()

    def quitApp_(self, sender):
        self.app.quit()



class App:
    def __init__(self):
        self.store = Store()
        self.engine = Engine(self.store)
        self.judge = Judge(self.store, self.engine)
        self.guard = watcher.Guard(self.store, self.judge)
        self.api = Api(self)
        self.window = None
        self.status_item = None
        self.menu_target = None
        self.quitting = False

    # ---------- window ----------
    def show_window(self):
        if self.window:
            self.window.show()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def on_closing(self):
        # If a PIN-locked session is running, don't let the window close; nudge the user.
        if not self.quitting and self.store.data.get('session') and self.store.data.get('pin'):
            try:
                self.window.evaluate_js("showToast('End your study session (with the PIN) before quitting.')")
            except Exception:
                pass
            return False
        # Otherwise, closing the window quits HonestHands cleanly.
        self.quitting = True
        self.engine.stop_server()
        AppHelper.callAfter(self._terminate)
        return True

    def _terminate(self):
        import os as _os
        _os._exit(0)

    # ---------- menu bar ----------
    @staticmethod
    def _hand_image(active):
        # Draw an open hand as a TEMPLATE image so macOS tints it for the menu bar
        # (black on light menu bars, white on dark). A brass dot marks an active session.
        W = H = 18.0
        img = NSImage.alloc().initWithSize_((W, H))
        img.lockFocus()
        NSColor.blackColor().set()  # template images are drawn in black; macOS recolors them
        path = NSBezierPath.bezierPath()
        path.appendBezierPath_(NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(4.6, 1.8, 8.4, 8.0), 3.0, 3.0))
        for x, y, hh in [(5.6, 7.2, 6.6), (7.8, 7.2, 7.8), (10.0, 7.2, 7.3), (12.0, 6.9, 6.0)]:
            path.appendBezierPath_(NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(x, y, 1.8, hh), 0.9, 0.9))
        thumb = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(2.4, 3.8, 1.8, 4.8), 0.9, 0.9)
        t = __import__('AppKit').NSAffineTransform.transform()
        t.translateXBy_yBy_(3.3, 6.2); t.rotateByDegrees_(34); t.translateXBy_yBy_(-3.3, -6.2)
        thumb.transformUsingAffineTransform_(t)
        path.appendBezierPath_(thumb)
        path.fill()
        img.unlockFocus()
        img.setTemplate_(True)
        if not active:
            return img
        # Active: composite the (already template-tinted) hand with a brass dot on top.
        comp = NSImage.alloc().initWithSize_((W, H))
        comp.lockFocus()
        img.drawInRect_fromRect_operation_fraction_(NSMakeRect(0, 0, W, H), NSMakeRect(0, 0, W, H), 2, 1.0)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.78, 0.63, 0.30, 1.0).set()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(12.0, 12.0, 5.0, 5.0)).fill()
        comp.unlockFocus()
        comp.setTemplate_(False)  # keep the brass dot its real color
        return comp

    def build_menu(self):
        if self.status_item is None:
            self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
            self.menu_target = MenuTarget.alloc().initWithApp_(self)
        cls, asg = self.store.session_targets()
        menu = NSMenu.alloc().init()
        title = (f'Guarding {cls["name"]}' + (f' / {asg["name"]}' if asg else '')) if cls else 'Not in a study session'
        header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, '')
        header.setEnabled_(False)
        menu.addItem_(header)
        menu.addItem_(NSMenuItem.separatorItem())
        for text, sel in (('Open HonestHands', 'openWindow:'), ('Quit', 'quitApp:')):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(text, sel, '')
            item.setTarget_(self.menu_target)
            menu.addItem_(item)
        self.status_item.setMenu_(menu)
        btn = self.status_item.button()
        btn.setTitle_('')
        btn.setImage_(self._hand_image(cls is not None))

    def refresh_menu(self):
        AppHelper.callAfter(self.build_menu)

    def quit(self):
        if self.store.data.get('session') and self.store.data.get('pin'):
            self.show_window()
            try:
                self.window.evaluate_js("showToast('End your study session (with the PIN) before quitting.')")
            except Exception:
                pass
            return
        self.quitting = True
        self.engine.stop_server()
        self._terminate()

    # ---------- startup ----------
    def setup_main_thread(self):
        self.build_app_menu()
        self.build_menu()
        watcher.has_accessibility(prompt=True)
        self.try_install_guard()

    def build_app_menu(self):
        # A minimal main menu so Cmd+Q works and quits cleanly.
        from AppKit import NSApp
        if self.menu_target is None:
            self.menu_target = MenuTarget.alloc().initWithApp_(self)
        mainmenu = NSMenu.alloc().init()
        appitem = NSMenuItem.alloc().init()
        mainmenu.addItem_(appitem)
        appmenu = NSMenu.alloc().init()
        q = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Quit HonestHands', 'quitApp:', 'q')
        q.setTarget_(self.menu_target)
        appmenu.addItem_(q)
        appitem.setSubmenu_(appmenu)
        NSApp().setMainMenu_(mainmenu)

    def try_install_guard(self):
        if not self.guard.install():
            # No permission yet: keep trying quietly until it's granted.
            threading.Timer(3.0, lambda: AppHelper.callAfter(self.try_install_guard)).start()

    def on_started(self):
        AppHelper.callAfter(self.setup_main_thread)
        self.engine.autostart()
        self.guard.start_typing_watch()
        try:
            bridge_server.start(self)
        except Exception as e:
            print('extension server not started:', e)


    # ----- browser-extension bridge -----
    def extension_active(self):
        '''The extension acts ONLY when the app is running AND a session is on.'''
        try:
            cls, _ = self.store.session_targets()
            return cls is not None
        except Exception:
            return False

    def extension_check(self, text, site, url):
        '''Judge a message the extension intercepted. Returns a verdict dict and logs it.
        Mirrors the Accessibility path so rules/log stay unified.'''
        cls, asg = self.store.session_targets()
        if cls is None:
            return {'verdict': 'allow'}
        text = (text or '').strip()
        if not text:
            return {'verdict': 'allow'}
        where = site or 'browser'
        r = self.judge.check(text, cls, asg, where, timeout=12)
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
            p = {'pid': 0, 'where': where, 'text': text}
            AppHelper.callAfter(watcher.HHPanel.show, self.guard, r, hard, p, cls, asg)
            return {'verdict': 'block' if hard else 'warn',
                    'reason': r.get('reason', ''), 'rule': r.get('rule', ''),
                    'quote': r.get('quote', ''), 'tip': r.get('tip', ''), 'hard': hard}
        return {'verdict': 'allow'}

    def run(self):
        if not ensure_single_instance():
            # Another HonestHands is already open; just bring it forward and quit quietly.
            try:
                from AppKit import NSRunningApplication, NSWorkspace
                me = NSRunningApplication.currentApplication().bundleIdentifier()
                for a in NSWorkspace.sharedWorkspace().runningApplications():
                    if a.bundleIdentifier() == me and a.processIdentifier() != NSRunningApplication.currentApplication().processIdentifier():
                        a.activateWithOptions_(1 << 1)
                        break
            except Exception:
                pass
            return
        self.window = webview.create_window(
            'HonestHands', url=resource('ui', 'index.html'), js_api=self.api,
            width=1060, height=740, min_size=(860, 600))
        self.window.events.closing += self.on_closing
        try:
            webview.start(self.on_started)
        finally:
            self.engine.stop_server()


if __name__ == '__main__':
    App().run()
