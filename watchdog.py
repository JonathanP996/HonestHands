"""A tiny watcher that keeps HonestHands running during a timed lock-in.

macOS (launchd) keeps THIS process alive; this process relaunches HonestHands if it finds it gone while the lock-in is still on.
As soon as the lock-in is over (time is up, a PIN or a friend released you) it removes itself. No heavy imports on purpose.
"""
import fcntl
import json
import os
import plistlib
import subprocess
import sys
import time


def locked(config_path, now=None):
    """Is a timed lock-in still running? (Reads the app's own saved settings.)"""
    try:
        with open(config_path) as f:
            s = (json.load(f).get('session') or {})
        return bool(s.get('locked') and s.get('ends_at', 0) > (now or time.time()))
    except Exception:
        return False


def app_running(lock_path):
    """The app holds an exclusive lock on this file while it runs; if we can take it, the app is not running."""
    try:
        f = open(lock_path, 'a')
    except OSError:
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        f.close()


def remove_self(label):
    path = os.path.expanduser(f'~/Library/LaunchAgents/{label}.plist')
    try:
        os.remove(path)
    except OSError:
        pass
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], capture_output=True)


def main(argv):
    opts = dict(zip(argv[::2], argv[1::2]))
    config, lock, label = opts['--config'], opts['--lock'], opts['--label']
    cmd = json.loads(opts['--cmd'])
    interval = float(opts.get('--interval', 3))
    while True:
        if not locked(config):
            remove_self(label)
            return 0
        if not app_running(lock):
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(8)                      # give it time to start before looking again
        time.sleep(interval)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
