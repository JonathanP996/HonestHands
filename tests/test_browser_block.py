#!/usr/bin/env python3
"""While a study session is on, AI websites in any browser except the guarded one are blocked.   python3 tests/test_browser_block.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import watcher

class FakeStore:
    def __init__(self, browser): self.data = {'browser': browser}; self.logged = []
    def session_targets(self): return {'id': 'c', 'name': 'ML', 'policy': 'tutor'}, None
    def log(self, e): self.logged.append(e)
class FakeAI:
    def cached(self, *a): return {'level': 'ok', 'hard': False, 'reasons': [], 'tip': '', 'verdict': 'allow', 'source': 'ai', 'ms': 1}
    class engine:
        @staticmethod
        def ready(): return True
watcher.AppHelper.callAfter = lambda fn, *a, **k: fn(*a, **k)       # run "on the main thread" immediately
shown = []
watcher.Guard.block_handler = lambda guard, r, hard, p, cls, asg: shown.append((r, hard))
bad = 0
def run(chosen, bundle, label):
    global bad
    shown.clear()
    g = watcher.Guard(FakeStore(chosen), FakeAI())
    watcher.current_prompt = lambda: {'where': 'gemini.google.com', 'text': 'give me the answer', 'pid': 1, 'app': 'x', 'bid': bundle}
    allowed = g.intercept('enter', None, {'id': 'c', 'name': 'ML', 'policy': 'tutor'}, None)
    return allowed, list(shown), g

for chosen, bundle, name, expect_block in [
        ('edge',    'com.google.Chrome',        'Edge chosen, typing in Chrome',            True),
        ('edge',    'com.apple.Safari',         'Edge chosen, typing in Safari',            True),
        ('edge',    'com.brave.Browser',        'Edge chosen, typing in Brave (unsupported)', True),
        ('edge',    'com.microsoft.edgemac',    'Edge chosen, typing in Edge',              False),
        ('safari',  'com.apple.Safari',         'Safari chosen, typing in Safari',          False),
        ('firefox', 'org.mozilla.firefoxdeveloperedition', 'Firefox chosen, Firefox Developer Edition', False),
        ('',        'com.brave.Browser',        'no browser chosen yet (nothing is blocked)', False)]:
    allowed, shown_now, g = run(chosen, bundle, name)
    blocked = bool(shown_now) and shown_now[0][0].get('source') == 'browser'
    ok = blocked == expect_block and (not blocked or (shown_now[0][1] is True and allowed is False and g.store.logged))
    bad += not ok
    msg = (shown_now[0][0]['reason'][:78] + '…') if blocked else 'allowed through to the normal check'
    print(('ok   ' if ok else 'FAIL ') + f'{name:48} -> {msg}')
print('\nALL PASSED' if not bad else f'\n{bad} FAILED'); sys.exit(1 if bad else 0)
