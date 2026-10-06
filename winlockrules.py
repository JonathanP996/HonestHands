"""The rule for which Windows programs are turned back during a session (no Windows calls: testable anywhere)."""
import browsers

BROWSER_EXES = {'chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe', 'vivaldi.exe', 'arc.exe'}
EXE_TO_KEY = {'chrome.exe': 'chrome', 'msedge.exe': 'edge', 'firefox.exe': 'firefox'}


def blocked_reason(exe, title, cfg, chosen, is_ai_app):
    """None if this program is fine to open, otherwise the sentence to show. Pure, so it can be tested anywhere."""
    exe = (exe or '').lower()
    if not exe:
        return None
    name = exe[:-4].capitalize() if exe.endswith('.exe') else exe
    if cfg.get('browsers', True) and chosen and exe in BROWSER_EXES and EXE_TO_KEY.get(exe) != chosen:
        return f'{name} is blocked while you’re locked in. Use {browsers.BROWSERS[chosen]["name"]} for AI during this session.'
    if cfg.get('ai_apps') and is_ai_app(exe, title):
        return f'{name} is blocked while you’re locked in. Finish your session first, or use your guarded browser.'
    if exe in [str(x).lower() for x in (cfg.get('apps') or [])]:
        return f'{name} is blocked while you’re locked in.'
    return None
