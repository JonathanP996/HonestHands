"""Stay locked in: while a study session is on, switching to a blocked app is turned back.

How the big proctoring tools do it, and what is realistic here:
  - Respondus LockDown Browser replaces your browser with a kiosk that takes over the screen.
  - Honorlock is a browser extension plus webcam/screen recording that flags tab switches for review.
  Neither is unbreakable on a computer you control. HonestHands watches which app comes to the front and, if it is one you've
  chosen to block, hides it and puts you back where you were, with a short note. It's a speed bump for the moment of temptation,
  not a cage: someone determined can still quit the app (a PIN stops that, if you set one).
"""
import os
import threading
import time

import browsers


def blocked_reason(bid, name, cfg, chosen_browser, is_ai_app):
    """None if this app is fine to open, otherwise the sentence to show. Pure, so it can be tested."""
    if not bid:
        return None
    if cfg.get('browsers', True) and chosen_browser and bid in _all_browser_ids() and browsers.key_for_bundle(bid) != chosen_browser:
        return f'{name} is blocked while you’re locked in. Use {browsers.BROWSERS[chosen_browser]["name"]} for AI during this session.'
    if cfg.get('ai_apps') and is_ai_app(bid, name):
        return f'{name} is blocked while you’re locked in. Finish your session first, or use your guarded browser.'
    if bid in (cfg.get('apps') or []):
        return f'{name} is blocked while you’re locked in.'
    return None


def _all_browser_ids():
    import watcher
    return watcher.BROWSERS


class SessionLock:
    def __init__(self, store, on_block, is_ai_app):
        self.store, self.on_block, self.is_ai_app = store, on_block, is_ai_app
        self.last_ok = None            # the last allowed app that was in front: where to put you back
        self._observer = None
        self.blocked = 0
        self._last_msg = {}            # app name -> when we last told them (so repeated tries don't stack popups)

    def active(self):
        cls, _ = self.store.session_targets()
        return cls is not None

    def start(self):
        """Call on the main thread. Registers for 'an app came to the front' notifications."""
        from AppKit import NSWorkspace, NSWorkspaceDidActivateApplicationNotification
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        self._observer = center.addObserverForName_object_queue_usingBlock_(NSWorkspaceDidActivateApplicationNotification, None, None, self._activated)
        threading.Thread(target=self._watch_front, daemon=True).start()

    def _watch_front(self):
        """The activation notification can be missed (an app already in front on another screen or Space, a window brought up
        another way). So also look at what is in front a couple of times a second while a session is on."""
        from AppKit import NSWorkspace
        from PyObjCTools import AppHelper
        while True:
            time.sleep(0.5)
            try:
                if not self.active():
                    continue
                cfg = self.store.data.get('lock') or {}
                chosen = self.store.data.get('browser') or ''
                front = NSWorkspace.sharedWorkspace().frontmostApplication()
                for app in NSWorkspace.sharedWorkspace().runningApplications():
                    if app.activationPolicy() != 0 or app.processIdentifier() == os.getpid():
                        continue                                   # only real apps with windows
                    bid, name = app.bundleIdentifier(), str(app.localizedName() or 'That app')
                    if not blocked_reason(bid, name, cfg, chosen, self.is_ai_app):
                        continue
                    if front is not None and app.processIdentifier() == front.processIdentifier():
                        AppHelper.callAfter(self.handle, bid, name, app)     # in front: turn them back, with the note
                    elif not app.isHidden():
                        AppHelper.callAfter(app.hide)                        # open behind something else: still out of sight
            except Exception as e:
                print('[lock] front check problem:', e, flush=True)

    def _activated(self, note):
        try:
            app = note.userInfo()['NSWorkspaceApplicationKey']
            self.handle(app.bundleIdentifier(), str(app.localizedName() or 'That app'), app)
        except Exception as e:
            print('[lock] could not check the app that opened:', e, flush=True)

    def handle(self, bid, name, app):
        if app is not None and app.processIdentifier() == os.getpid():
            return                                          # never block ourselves
        cfg = self.store.data.get('lock') or {}
        reason = blocked_reason(bid, name, cfg, self.store.data.get('browser') or '', self.is_ai_app) if self.active() else None
        if reason is None:
            self.last_ok = bid or self.last_ok
            return
        self.blocked += 1
        try:
            app.hide()                                      # out of sight
        except Exception:
            pass
        self._return_to_work()
        if time.time() - self._last_msg.get(name, 0) > 4:
            self._last_msg[name] = time.time()
            self.on_block(reason, name)
        # still in front a moment later (it ignored the first hide)? hide it again
        threading.Timer(0.35, self._recheck, args=(app,)).start()

    def _recheck(self, app):
        try:
            if not app.isHidden():
                from PyObjCTools import AppHelper
                AppHelper.callAfter(app.hide)
                AppHelper.callAfter(self._return_to_work)
        except Exception:
            pass

    def _return_to_work(self):
        """Bring the guarded browser (or wherever you were) back to the front."""
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
        chosen = self.store.data.get('browser') or ''
        for bid in ([browsers.BROWSERS[chosen]['bundle']] if chosen else []) + ([self.last_ok] if self.last_ok else []):
            for a in NSRunningApplication.runningApplicationsWithBundleIdentifier_(bid) or []:
                if a.activateWithOptions_(NSApplicationActivateIgnoringOtherApps):
                    return
