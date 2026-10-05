#!/usr/bin/env python3
"""The 'can't quit during a timed lock-in' mechanism, tested with a stand-in program (never touches the real app).   python3 tests/test_keepalive.py"""
import fcntl, json, os, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import keepalive, watchdog

bad = 0
def check(cond, msg):
    global bad; print(('ok   ' if cond else 'FAIL ') + msg); bad += (not cond)

tmp = Path(tempfile.mkdtemp()); cfg = tmp / 'config.json'; lock = tmp / 'app.lock'; marker = tmp / 'launched'
def write(session): cfg.write_text(json.dumps({'session': session}))

now = time.time()
write({'locked': True, 'ends_at': now + 600}); check(watchdog.locked(cfg), 'a running timed lock-in counts as locked')
write({'locked': True, 'ends_at': now - 5});   check(not watchdog.locked(cfg), 'an expired lock-in is not locked')
write({'started': now});                         check(not watchdog.locked(cfg), 'an open-ended session is not a timed lock')
cfg.write_text('not json');                      check(not watchdog.locked(cfg), 'a damaged settings file is treated as unlocked (never trap someone)')
check(not watchdog.app_running(lock), 'no app holding the lock file: not running')
held = open(lock, 'a'); fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
check(watchdog.app_running(lock), 'the app holding the lock file is seen as running')
fcntl.flock(held, fcntl.LOCK_UN); held.close()

# 1) the watchdog relaunches the app when it is gone and the lock is still on, then exits when the lock ends
write({'locked': True, 'ends_at': time.time() + 600})
args = ['--config', str(cfg), '--lock', str(lock), '--label', 'app.honesthands.test.never-loaded', '--interval', '0.3',
        '--cmd', json.dumps(['/usr/bin/touch', str(marker)])]
p = subprocess.Popen([sys.executable, str(Path(keepalive.__file__).parent / 'main.py'), '--watchdog'] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
end = time.time() + 12
while time.time() < end and not marker.exists(): time.sleep(0.2)
check(marker.exists(), 'with the app gone and the lock on, the watchdog relaunches it')
write({'session': None}); end = time.time() + 20
while time.time() < end and p.poll() is None: time.sleep(0.3)
check(p.poll() == 0, 'when the lock-in ends, the watchdog exits by itself')
if p.poll() is None: p.kill()

# 2) launchd really keeps the watchdog alive: kill it hard and it comes back; then removing the job stops it for good
label = 'app.honesthands.keepalive.selftest'
pidfile = tmp / 'pid'
script = f'echo $$ > {pidfile}; exec sleep 600'
ok = keepalive.install(label, args=['/bin/sh', '-c', script])
time.sleep(1.5)
check(ok and keepalive.loaded(label), 'the launchd job installs and loads (no admin password needed)')
first = int(pidfile.read_text()); os.kill(first, 9); time.sleep(8)
second = int(pidfile.read_text()) if pidfile.exists() else 0
check(second and second != first, f'force-killing it does not work: launchd brought it back (pid {first} -> {second})')
keepalive.remove(label); time.sleep(1.5)
alive = subprocess.run(['kill', '-0', str(second)], capture_output=True).returncode == 0
check(not keepalive.loaded(label) and not keepalive.plist_path(label).exists() and not alive, 'removing the job stops it and cleans up completely')
if alive: os.kill(second, 9)
print('\nALL PASSED' if not bad else f'\n{bad} FAILED'); sys.exit(1 if bad else 0)
