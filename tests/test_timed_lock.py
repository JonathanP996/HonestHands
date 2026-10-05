#!/usr/bin/env python3
"""The rules of a timed lock-in (start needs a way out; leave early only by PIN or a friend; ends by itself).   python3 tests/test_timed_lock.py"""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import store as storemod
tmp = Path(tempfile.mkdtemp()); storemod.APP_DIR = tmp; storemod.CONFIG = tmp / 'config.json'; storemod.LOG = tmp / 'log.jsonl'
import keepalive, bridge, watcher
calls = []; keepalive.install = lambda *a, **k: calls.append('install'); keepalive.remove = lambda *a, **k: calls.append('remove')
watcher.notify = lambda *a, **k: calls.append('notify')

class Cloud:
    friends = 0; signed_in = False; c = {}; inbox = {'unread': 0, 'requests': 0}
    def exit_paths(self): return {'pin': bool(S.data.get('pin')), 'friends': self.friends}
    def releasers(self): return []
class AI:
    def warm(self, *a): pass
    def forget(self): pass
class _Eng:
    @staticmethod
    def status(): return {'ready': True}
class _Guard: watching = False
class App:
    cloud = Cloud(); ai_guard = AI(); engine = _Eng(); guard = _Guard()
    def extension_seen_recently(self, *a): return False
    def refresh_menu(self): pass
    def locked_now(self):
        s = S.data.get('session') or {}
        return bool(s.get('locked') and s.get('ends_at', 0) > time.time())
S = storemod.Store()
S.data['classes'] = [{'id': 'c1', 'name': 'ML', 'policy': 'tutor', 'assignments': []}]
app = App(); api = bridge.Api.__new__(bridge.Api)
api.__dict__['_app'] = app
bridge.Api._store = property(lambda self: S)

bad = 0
def check(cond, msg):
    global bad; print(('ok   ' if cond else 'FAIL ') + msg); bad += (not cond)
def reset(pin='', friends=0): S.data['session'] = None; S.data['pin'] = pin; Cloud.friends = friends; calls.clear()

reset(); r = api.start_session('c1', '', 'warn', 30)
check('error' in r and 'way out' in r['error'] and not S.data['session'] and 'install' not in calls, 'a timed lock cannot start with no PIN and no friend (so nobody traps themselves)')
r = api.start_session('c1', '', 'warn', 5000); check('error' in r, 'more than 12 hours is refused')
r = api.start_session('c1', '', 'warn', 0); check('error' not in r and not S.data['session'].get('locked') and not app.locked_now(), 'no timer: an ordinary open-ended session (not locked)')
api.end_session(''); 

reset(pin='1234'); r = api.start_session('c1', '', 'warn', 30)
s = S.data['session']; check('error' not in r and s['locked'] and abs(s['ends_at'] - (time.time() + 1800)) < 5 and calls[:1] == ['install'], 'with a PIN a 30-minute lock starts and installs the keep-alive watcher')
check(r['session']['locked'] and r['session']['minutes'] == 30 and r['session']['ends_at'] == s['ends_at'], 'the app state reports the lock and when it ends')
r = api.end_session('9999'); check('error' in r and S.data['session'], 'ending early with the wrong PIN is refused')
r = api.end_session(''); check('error' in r and S.data['session'], 'ending early with no PIN is refused')
calls.clear(); r = api.end_session('1234'); check('error' not in r and not S.data['session'] and 'remove' in calls, 'the right PIN ends it and removes the watcher')
ev = [e for e in S.read_log() if e.get('event') == 'session end'][-1]; check(ev.get('reason') == 'ended early with the PIN', 'the log records how it ended')

reset(friends=2); r = api.start_session('c1', '', 'warn', 45)
check('error' not in r and S.data['session']['locked'], 'with friends but no PIN a timed lock can start')
r = api.end_session(''); check('error' in r and 'friend' in r['error'], 'without a PIN, only a friend can release you (and the message says so)')
app.api = api; calls.clear(); api._finish_session('Bob released you', ended_by='Bob released you')
check(not S.data['session'] and 'remove' in calls and 'notify' in calls, 'a friend\'s release ends the lock, removes the watcher and notifies')

reset(pin='1234'); api.start_session('c1', '', 'warn', 10)
check(api.finish_if_due() is False and S.data['session'], 'before the time is up, nothing ends')
S.data['session']['ends_at'] = time.time() - 1; calls.clear()
check(api.finish_if_due() is True and not S.data['session'] and 'remove' in calls and 'notify' in calls, 'when the time is up it ends by itself (and tidies up)')
check(not app.locked_now(), 'and the app no longer counts as locked')

reset(pin='1234'); api.start_session('c1', '', 'warn', 0)
check(api.end_session('0000').get('error') and api.end_session('1234').get('error') is None, 'an open-ended session with a PIN still needs the PIN to end')
print('\nALL PASSED' if not bad else f'\n{bad} FAILED'); sys.exit(1 if bad else 0)
