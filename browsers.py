"""The browsers HonestHands supports, and how to tell them apart.

During a study session you pick ONE guarded browser. AI websites in any other browser are blocked (the send is held), so
there is no easy way around the extension by opening a different browser.
"""
BROWSERS = {
    'chrome':  {'name': 'Google Chrome',  'bundle': 'com.google.Chrome',    'kind': 'chromium', 'app': 'Google Chrome',  'page': 'chrome://extensions', 'winexe': 'chrome'},
    'edge':    {'name': 'Microsoft Edge', 'bundle': 'com.microsoft.edgemac', 'kind': 'chromium', 'app': 'Microsoft Edge', 'page': 'edge://extensions', 'winexe': 'msedge'},
    'firefox': {'name': 'Firefox',        'bundle': 'org.mozilla.firefox',   'kind': 'firefox',  'app': 'Firefox',        'page': 'about:debugging#/runtime/this-firefox', 'winexe': 'firefox'},
    'safari':  {'name': 'Safari',         'bundle': 'com.apple.Safari',      'kind': 'safari',   'app': 'Safari',         'page': ''},
}
# beta / developer builds count as the same browser
_ALIASES = {'com.google.Chrome.beta': 'chrome', 'com.google.Chrome.canary': 'chrome', 'com.microsoft.edgemac.Beta': 'edge',
            'com.microsoft.edgemac.Dev': 'edge', 'org.mozilla.firefoxdeveloperedition': 'firefox', 'com.apple.SafariTechnologyPreview': 'safari'}
BUNDLE_TO_KEY = dict({v['bundle']: k for k, v in BROWSERS.items()}, **_ALIASES)


def key_for_bundle(bundle_id):
    """'chrome' / 'edge' / 'firefox' / 'safari', or None for any other browser (Brave, Arc, Opera...)."""
    return BUNDLE_TO_KEY.get(bundle_id or '')


def is_installed(key):
    from platform_info import IS_WIN
    if IS_WIN:
        exe = BROWSERS[key].get('winexe')
        if not exe:
            return False
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    winreg.CloseKey(winreg.OpenKey(root, rf'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}.exe'))
                    return True
                except OSError:
                    continue
        except Exception:
            pass
        return False
    try:
        from AppKit import NSWorkspace
        return NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(BROWSERS[key]['bundle']) is not None
    except Exception:
        return False


def options():
    from platform_info import IS_WIN
    return [dict(key=k, name=v['name'], kind=v['kind'], installed=is_installed(k)) for k, v in BROWSERS.items() if not (IS_WIN and k == 'safari')]


def wrong_browser(chosen, bundle_id):
    """True if a guarded browser is chosen and this isn't it."""
    return bool(chosen) and key_for_bundle(bundle_id) != chosen
