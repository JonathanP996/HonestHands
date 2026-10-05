"""AI Integrity Guard: the Mac app."""
import os
import sys

if len(sys.argv) > 1 and sys.argv[1] == '--watchdog':      # the timed-lock watcher: no UI, no heavy imports
    import watchdog
    raise SystemExit(watchdog.main(sys.argv[2:]))
import threading
import time

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
from ai_guard import AIGuard
import cloud
import keepalive
import lock
import updates
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



class OverlayApi:
    def __init__(self, app):
        self._app = app
    def choose(self, choice):
        return self._app.overlay_choose(choice)


class App:
    def __init__(self):
        self.store = Store()
        if os.environ.get('HH_RESET_PIN') == '1' and self.store.data.get('pin'):
            self.store.data['pin'] = ''   # developer escape hatch for a forgotten PIN
            self.store.save()
            print('Accountability PIN cleared (HH_RESET_PIN=1).')
        self.engine = Engine(self.store)
        self.ai_guard = AIGuard(self.store, self.engine)
        self.guard = watcher.Guard(self.store, self.ai_guard)
        self.api = None
        self.cloud = cloud.Cloud(self.store, self)
        self.updater = updates.Updater(self.store, self._update_found)
        self.lock = lock.SessionLock(self.store, self._lock_message, watcher.is_ai_app)
        watcher.Guard.on_override = self.cloud.kick
        self.api = Api(self)
        self.cloud.app = self
        self.window = None
        self.status_item = None
        self.menu_target = None
        self.quitting = False
        self._ext_last_ping = 0.0
        self._ext_pings = {}        # browser key -> time of the extension's last check-in

    def _update_found(self, latest):
        watcher.notify('HonestHands', f"A new version is ready{(' (' + latest['version'] + ')') if latest.get('version') else ''}. Open HonestHands to update.")

    # ---------- timed lock-in ----------
    def locked_now(self):
        s = self.store.data.get('session') or {}
        return bool(s.get('locked') and s.get('ends_at', 0) > time.time())

    def release_session(self, why):
        """A friend released the student (or time ran out): end the lock-in."""
        self.api._finish_session(why, ended_by=why)

    def _lock_tick(self):
        """Every couple of seconds: finish a lock-in whose time is up, and keep the menu bar's countdown fresh."""
        last_menu = 0
        while True:
            time.sleep(2)
            try:
                s = self.store.data.get('session') or {}
                if self.api.finish_if_due():
                    pass
                elif s.get('locked') and time.time() - last_menu > 30:
                    last_menu = time.time()
                    self.refresh_menu()
            except Exception as e:
                print('[lock] tick problem:', e, flush=True)

    def _need_out(self):
        """Bring the window forward and open the 'Need out?' sheet (PIN or ask a friend)."""
        self.show_window()
        try:
            self.window.evaluate_js("typeof openNeedOut === 'function' && openNeedOut()")
        except Exception:
            pass

    # ---------- window ----------
    def show_window(self):
        if self.window:
            self.window.show()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def on_closing(self):
        if not self.quitting and self.locked_now():
            try:
                self.window.hide()                  # a lock-in keeps HonestHands running; closing just tucks the window away
            except Exception:
                pass
            return False
        # An open-ended session with a PIN can't be closed away either.
        if not self.quitting and self.store.data.get('session') and self.store.data.get('pin'):
            self._need_out()
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
        from AppKit import NSGraphicsContext
        ctx = NSGraphicsContext.currentContext()
        ctx.setCompositingOperation_(0)   # NSCompositingOperationClear: a nail-hole through the palm
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(7.9, 4.6, 2.4, 2.4)).fill()
        ctx.setCompositingOperation_(2)                         # back to normal drawing
        img.unlockFocus()
        img.setTemplate_(True)
        if not active:
            return img
        # Active: composite the (already template-tinted) hand with a brass dot on top.
        comp = NSImage.alloc().initWithSize_((W, H))
        comp.lockFocus()
        img.drawInRect_fromRect_operation_fraction_(NSMakeRect(0, 0, W, H), NSMakeRect(0, 0, W, H), 2, 1.0)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.79, 0.60, 0.80, 1.0).set()
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
        s = self.store.data.get('session') or {}
        if cls and s.get('ends_at') and s['ends_at'] > time.time():
            title = f'Locked in · {cls["name"]} · {max(1, int((s["ends_at"] - time.time()) / 60))} min left'
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
        if self.locked_now() or (self.store.data.get('session') and self.store.data.get('pin')):
            self._need_out()
            return
        self.quitting = True
        self.engine.stop_server()
        if getattr(self, 'native_overlay', None):
            self.native_overlay.close()
        keepalive.remove()
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
        self.cloud.start()
        self.updater.start()
        threading.Thread(target=self._lock_tick, daemon=True).start()
        (keepalive.install if self.locked_now() else keepalive.remove)()     # a stale watcher must never outlive its lock-in
        AppHelper.callAfter(self.lock.start)           # app-switch notifications must be registered on the main thread
        def _warm_when_ready():
            import time as _t
            for _ in range(240):
                if self.engine.ready():
                    c, a = self.store.session_targets()
                    if c:
                        self.ai_guard.warm(c, a)
                    return
                _t.sleep(0.5)
        threading.Thread(target=_warm_when_ready, daemon=True).start()
        self.guard.start_typing_watch()
        watcher.Guard.block_handler = self.show_overlay_block
        try:
            import overlay_client
            self.native_overlay = overlay_client.create_backend()
            watcher.Guard.overlay_hook = self.native_overlay
        except Exception as e:
            print('native overlay unavailable:', e)
            self.native_overlay = None
        if self.native_overlay is None:
            AppHelper.callAfter(self.setup_overlay)
        try:
            bridge_server.start(self)
        except Exception as e:
            print('extension server not started:', e)


    # ----- Wispr-style overlay -----
    def setup_overlay(self):
        base = dict(url=resource('ui', 'overlay.html'), js_api=OverlayApi(self),
                    frameless=True, easy_drag=False, on_top=True, hidden=True,
                    width=520, height=320)
        import inspect
        sig = set(inspect.signature(webview.create_window).parameters)
        for k, v in (('transparent', True), ('background_color', '#00000000'),
                     ('focus', False), ('resizable', False)):
            if k in sig:
                base[k] = v
        try:
            self.overlay = webview.create_window('HonestHands Overlay', **base)
        except TypeError:
            for k in ('transparent', 'background_color', 'focus', 'resizable'):
                base.pop(k, None)
            self.overlay = webview.create_window('HonestHands Overlay', **base)
        self._overlay_ready = False
        try:
            self.overlay.events.loaded += self._overlay_loaded
        except Exception:
            self._overlay_ready = True
        AppHelper.callLater(0.6, self._style_overlay_window)

    def _overlay_loaded(self):
        self._overlay_ready = True
        self._style_overlay_window()

    def _style_overlay_window(self):
        # Make the overlay a transparent, click-through-friendly, always-on-top window
        # that floats over full-screen apps — the Wispr approach.
        try:
            from AppKit import (NSApp, NSScreen, NSStatusWindowLevel, NSColor,
                                NSWindowCollectionBehaviorCanJoinAllSpaces,
                                NSWindowCollectionBehaviorFullScreenAuxiliary,
                                NSWindowCollectionBehaviorStationary)
            for win in NSApp().windows():
                if str(win.title()) == 'HonestHands Overlay':
                    win.setLevel_(NSStatusWindowLevel)
                    win.setOpaque_(False)
                    win.setBackgroundColor_(NSColor.clearColor())
                    win.setHasShadow_(False)
                    win.setCollectionBehavior_(
                        NSWindowCollectionBehaviorCanJoinAllSpaces
                        | NSWindowCollectionBehaviorFullScreenAuxiliary
                        | NSWindowCollectionBehaviorStationary)
                    win.setIgnoresMouseEvents_(False)
                    self._overlay_win = win
                    self._position_overlay()
                    break
        except Exception as e:
            print('overlay style note:', e)

    def _position_overlay(self):
        try:
            win = getattr(self, '_overlay_win', None)
            if win is None:
                return
            from AppKit import NSScreen
            scr = NSScreen.mainScreen().frame()
            fr = win.frame()
            x = scr.origin.x + (scr.size.width - fr.size.width) / 2.0   # center
            y = scr.origin.y + 70                                        # bottom-ish (Wispr-style)
            win.setFrameOrigin_((x, y))
        except Exception as e:
            print('overlay position note:', e)

    def show_overlay_block(self, guard, r, hard, p, cls, asg):
        import json as _json
        native = getattr(self, 'native_overlay', None)
        if native is not None:
            reason = r.get('reason') or (r.get('reasons') or ['This looks like it breaks a rule for this class.'])[0]
            payload = {
                'hard': bool(hard), 'title': 'Message blocked' if hard else 'Hold on a second',
                'context': cls['name'] + (f' / {asg["name"]}' if asg else '') + ' · ' + p.get('where', ''),
                'reason': reason, 'rule': r.get('rule', ''), 'quote': r.get('quote', ''), 'tip': r.get('tip', ''),
                'source': 'AI guard' if r.get('source') == 'ai' else 'keyword rules',
                'allowSend': not hard,
            }
            def on_choice(choice, _p=p, _g=guard, _cls=cls, _asg=asg):
                _g.on_panel_choice('send_anyway' if choice == 'send_anyway' else 'edit', _p)
            if native.show(payload, on_choice):
                return
        self._pending_block = {'guard': guard, 'p': p}
        payload = {
            'hard': bool(hard),
            'reason': r.get('reason') or (r.get('reasons') or ['This looks like it breaks a rule for this class.'])[0],
            'rule': r.get('rule', ''), 'quote': r.get('quote', ''), 'tip': r.get('tip', ''),
            'where': p.get('where', ''), 'source': 'AI guard' if r.get('source') == 'ai' else 'keyword rules',
            'class': cls['name'], 'assignment': asg['name'] if asg else '',
        }
        if not getattr(self, '_overlay_ready', False):
            guard._release()
            return
        try:
            self.overlay.show()
            self._style_overlay_window()
            self.overlay.evaluate_js('showBlock(' + _json.dumps(payload) + ')')
        except Exception as e:
            print('show_overlay_block error:', e)
            guard._release()

    def overlay_choose(self, choice):
        pb = getattr(self, '_pending_block', None)
        try:
            self.overlay.hide()
        except Exception:
            pass
        if pb:
            self._pending_block = None
            pb['guard'].on_panel_choice('send_anyway' if choice == 'send_anyway' else 'edit', pb['p'])
        return True

    # ----- in-app block UI (legacy, unused) -----
    def show_block_in_app(self, guard, r, hard, p, cls, asg):
        import json as _json
        self._pending_block = {'guard': guard, 'p': p}
        payload = {
            'hard': bool(hard),
            'reason': r.get('reason') or (r.get('reasons') or ['This looks like it breaks a rule for this class.'])[0],
            'rule': r.get('rule', ''), 'quote': r.get('quote', ''), 'tip': r.get('tip', ''),
            'where': p.get('where', ''), 'source': 'AI guard' if r.get('source') == 'ai' else 'keyword rules',
            'class': cls['name'], 'assignment': asg['name'] if asg else '',
        }
        # Bring the app to the front (this is a normal activation — easy and reliable).
        self.show_window()
        try:
            self.window.evaluate_js('showBlock(' + _json.dumps(payload) + ')')
        except Exception as e:
            print('show_block_in_app error:', e)
            guard._release()

    def resolve_block(self, choice):
        pb = getattr(self, '_pending_block', None)
        if not pb:
            return True
        self._pending_block = None
        pb['guard'].on_panel_choice('send_anyway' if choice == 'send_anyway' else 'edit', pb['p'])
        return True

    def _lock_message(self, reason, app_name):
        """Tell the student why they were turned back, and note it in the activity log."""
        cls, asg = self.store.session_targets()
        self.store.log({'t': time.time(), 'event': 'turned back from ' + app_name, 'class': cls['name'] if cls else '', 'assignment': ''})
        payload = {'hard': True, 'title': 'You’re locked in', 'context': (cls['name'] if cls else 'Study session') + ' · ' + app_name,
                   'reason': reason, 'rule': '', 'quote': '', 'tip': '', 'source': 'session lock', 'allowSend': False,
                   'okLabel': 'Back to work', 'note': 'End your session from HonestHands if you’re done.'}
        native = getattr(self, 'native_overlay', None)
        if native is not None:
            AppHelper.callAfter(lambda: native.show(payload, lambda choice: None))
        else:
            watcher.notify('HonestHands', reason)

    # ----- browser-extension bridge -----
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
            AppHelper.callAfter(hook.checking)
        sa = getattr(self.guard, 'sent_anyway', None)
        if sa and sa[0].strip() == text and time.time() < sa[1]:
            return {'verdict': 'allow'}
        if has_pic:
            r = self.ai_guard.check_with_images(text, images, cls, asg, where, timeout=15, n_images=n_images)
            text = (text + ' ' if text else '') + f'[+{max(len(images), n_images)} picture{"s" if max(len(images), n_images) != 1 else ""}]'
        else:
            r = self.ai_guard.check(text, cls, asg, where, timeout=12)
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
            AppHelper.callAfter(self.show_overlay_block if getattr(self, 'native_overlay', None) else watcher.HHPanel.show,
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
            AppHelper.callAfter(hook.ok)
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
