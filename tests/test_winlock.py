"""Which Windows programs get turned back during a session (the rule only; the window handling needs Windows)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from winlockrules import blocked_reason

bad = 0
def check(ok, msg):
    global bad
    print(('ok   ' if ok else 'FAIL ') + msg); bad += 0 if ok else 1

ai = lambda exe, title: 'chatgpt' in (exe + title).lower()
cfg = {'browsers': True, 'ai_apps': False}
check(blocked_reason('chrome.exe', '', cfg, 'chrome', ai) is None, 'the guarded browser is fine')
r = blocked_reason('msedge.exe', '', cfg, 'chrome', ai)
check(bool(r) and 'Google Chrome' in r, 'another browser is turned back, and the note names the guarded one')
check(blocked_reason('brave.exe', '', cfg, 'firefox', ai) is not None, 'browsers not on the supported list are turned back too')
check(blocked_reason('msedge.exe', '', cfg, '', ai) is None, 'no guarded browser chosen: nothing is blocked')
check(blocked_reason('msedge.exe', '', {'browsers': False}, 'chrome', ai) is None, 'with the browser block off, other browsers are fine')
check(blocked_reason('chatgpt.exe', '', cfg, 'chrome', ai) is None, 'AI apps stay allowed by default (the guard checks what you send)')
check(blocked_reason('chatgpt.exe', '', {'browsers': True, 'ai_apps': True}, 'chrome', ai) is not None, 'AI apps are blocked when you turn that on')
check(blocked_reason('notepad.exe', '', {'apps': ['Notepad.exe']}, 'chrome', ai) is not None, 'a custom blocked program is blocked (any capitals)')
check(blocked_reason('', '', cfg, 'chrome', ai) is None, 'unknown programs are left alone')
print('ALL PASSED' if not bad else 'FAILURES: %d' % bad)
sys.exit(1 if bad else 0)
