"""Alerts that come from HonestHands itself: the app's own icon, and clicking one opens the app on the right tab.

The old way (AppleScript's 'display notification') shows up as Script Editor. UNUserNotificationCenter needs the real signed
app bundle, so when run from source (python main.py) this quietly falls back to the old way."""
import subprocess
import uuid

_center = None
_delegate = None
_on_click = None
_granted = None            # None until macOS answers the permission question


def available():
    try:
        from Foundation import NSBundle
        b = NSBundle.mainBundle()
        return b.bundleIdentifier() == 'com.honesthands.app' and str(b.bundlePath()).endswith('.app')
    except Exception:
        return False


def setup(on_click):
    """Call on the main thread, once. on_click(action) is called with 'messages' / 'community' / ... when an alert is clicked."""
    global _center, _delegate, _on_click
    if _center is not None or not available():
        return _center is not None
    try:
        import objc
        import UserNotifications as UN
        from Foundation import NSObject
        _on_click = on_click

        class Delegate(NSObject, protocols=[objc.protocolNamed('UNUserNotificationCenterDelegate')]):
            def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, notification, handler):
                handler(UN.UNNotificationPresentationOptionBanner | UN.UNNotificationPresentationOptionList | UN.UNNotificationPresentationOptionSound)

            def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(self, center, response, handler):
                try:
                    info = response.notification().request().content().userInfo() or {}
                    if _on_click:
                        _on_click(str(info.get('action') or ''))
                finally:
                    handler()

        _delegate = Delegate.alloc().init()
        _center = UN.UNUserNotificationCenter.currentNotificationCenter()
        _center.setDelegate_(_delegate)
        def answered(granted, err):
            global _granted
            _granted = bool(granted)
        _center.requestAuthorizationWithOptions_completionHandler_(
            UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound | UN.UNAuthorizationOptionBadge, answered)
        return True
    except Exception as e:
        print('[notify] could not start the app\'s own alerts:', e, flush=True)
        _center = None
        return False


def send(title, message, action=''):
    """True if it went out as one of the app's own alerts."""
    if _center is None or _granted is False:
        return False                      # not started, or they said no: the caller falls back to the old style alert
    try:
        import UserNotifications as UN
        c = UN.UNMutableNotificationContent.alloc().init()
        c.setTitle_(title)
        c.setBody_(message)
        c.setSound_(UN.UNNotificationSound.defaultSound())
        c.setUserInfo_({'action': action or ''})
        req = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(str(uuid.uuid4()), c, None)
        _center.addNotificationRequest_withCompletionHandler_(req, lambda err: None)
        return True
    except Exception as e:
        print('[notify] could not send:', e, flush=True)
        return False
