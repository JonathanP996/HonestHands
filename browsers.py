"""The browsers HonestHands supports, and how to tell them apart.

During a study session you pick ONE guarded browser. AI websites in any other browser are blocked (the send is held), so
there is no easy way around the extension by opening a different browser.
"""
BROWSERS = {
    'chrome':  {'name': 'Google Chrome',  'bundle': 'com.google.Chrome',    'kind': 'chromium', 'app': 'Google Chrome',  'page': 'chrome://extensions'},
    'edge':    {'name': 'Microsoft Edge', 'bundle': 'com.microsoft.edgemac', 'kind': 'chromium', 'app': 'Microsoft Edge', 'page': 'edge://extensions'},
    'firefox': {'name': 'Firefox',        'bundle': 'org.mozilla.firefox',   'kind': 'firefox',  'app': 'Firefox',        'page': 'about:debugging#/runtime/this-firefox'},
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
    try:
        from AppKit import NSWorkspace
        return NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(BROWSERS[key]['bundle']) is not None
    except Exception:
        return False


def options():
    return [dict(key=k, name=v['name'], kind=v['kind'], installed=is_installed(k)) for k, v in BROWSERS.items()]


def wrong_browser(chosen, bundle_id):
    """True if a guarded browser is chosen and this isn't it."""
    return bool(chosen) and key_for_bundle(bundle_id) != chosen
