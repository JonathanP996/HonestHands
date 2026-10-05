#!/usr/bin/env python3
"""The app lock.   python3 tests/test_lock.py          (rules only)
                   python3 tests/test_lock.py --live   (also checks the real macOS notification, briefly hiding Finder)"""
import subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lock, watcher

bad = 0
def check(cond, msg):
    global bad; print(('ok   ' if cond else 'FAIL ') + msg); bad += (not cond)

cfg_on = {'browsers': True, 'ai_apps': False}
ai = watcher.is_ai_app
r = lambda bid, name, cfg=cfg_on, chosen='edge': lock.blocked_reason(bid, name, cfg, chosen, ai)
check(r('com.google.Chrome', 'Google Chrome') and 'Microsoft Edge' in r('com.google.Chrome', 'Google Chrome'), 'Edge chosen: opening Chrome is blocked and the note names Edge')
check(r('com.apple.Safari', 'Safari') is not None, 'Edge chosen: opening Safari is blocked')
check(r('com.brave.Browser', 'Brave Browser') is not None, 'Edge chosen: an unsupported browser (Brave) is blocked')
check(r('com.microsoft.edgemac', 'Microsoft Edge') is None, 'the guarded browser itself is fine')
check(r('com.apple.finder', 'Finder') is None and r('com.apple.Terminal', 'Terminal') is None and r('com.microsoft.Word', 'Word') is None, 'everyday apps (Finder, Terminal, Word) are never touched')
check(r('com.google.Chrome', 'Google Chrome', chosen='') is None, 'no guarded browser chosen: nothing is blocked')
check(r('com.google.Chrome', 'Google Chrome', cfg={'browsers': False}) is None, 'with the switch off, other browsers are allowed')
check(r('com.anthropic.claudefordesktop', 'Claude') is None, 'AI desktop apps are allowed by default (the guard checks what you send from them)')
check(r('com.anthropic.claudefordesktop', 'Claude', cfg={'browsers': True, 'ai_apps': True}) is not None, 'with "block AI desktop apps" on, Claude is blocked')
check(r('com.example.game', 'Some Game', cfg={'apps': ['com.example.game']}) is not None, 'a custom blocked app is blocked')

if '--live' in sys.argv:
    from AppKit import NSRunLoop, NSDate, NSRunningApplication
    class FakeStore:
        data = {'browser': '', 'lock': {'apps': ['com.apple.finder']}}
        def session_targets(self): return {'id': 'c', 'name': 'ML'}, None
    seen = []
    sl = lock.SessionLock(FakeStore(), lambda reason, name: seen.append((name, reason)), ai)
    sl.start()
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.5))
    subprocess.run(['open', '-a', 'Finder']); subprocess.run(['osascript', '-e', 'tell application "Finder" to activate'])
    end = time.time() + 6
    while time.time() < end and not seen:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.25))
    check(bool(seen) and seen[0][0] == 'Finder', f'live: macOS told us Finder came to the front and the lock reacted ({seen[0][1][:60] if seen else "no event"})')
    fin = NSRunningApplication.runningApplicationsWithBundleIdentifier_('com.apple.finder')[0]
    check(fin.isHidden(), 'live: the blocked app really was hidden')
    fin.unhide()
print('\nALL PASSED' if not bad else f'\n{bad} FAILED'); sys.exit(1 if bad else 0)
