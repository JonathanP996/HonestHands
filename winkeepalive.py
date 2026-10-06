"""Keeps HonestHands running during a timed lock-in on Windows.

A Task Scheduler job runs `--watchdog-once` every minute. That quick check (no heavy imports) relaunches the app if it is not
running while a lock-in is still on. The job is installed only for the length of a lock-in and removed when it ends."""
import json
import os
import socket
import subprocess
import sys
import time

TASK = 'HonestHandsKeepAlive'
APP_PORT = 7674          # the app holds this port while it runs (winmain.ensure_single_instance)


def app_command():
    """How to start HonestHands again: the installed program, or `python winmain.py` from source."""
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    return [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'winmain.py')]


def check_command():
    return app_command() + ['--watchdog-once']


def _q(parts):
    return ' '.join('"%s"' % p if ' ' in p else p for p in parts)


def install():
    subprocess.run(['schtasks', '/Create', '/TN', TASK, '/TR', _q(check_command()), '/SC', 'MINUTE', '/MO', '1', '/F'],
                   capture_output=True, creationflags=0x08000000)       # no console window


def remove():
    subprocess.run(['schtasks', '/Delete', '/TN', TASK, '/F'], capture_output=True, creationflags=0x08000000)


def locked(config_path, now=None):
    try:
        with open(config_path) as f:
            s = (json.load(f).get('session') or {})
        return bool(s.get('locked') and s.get('ends_at', 0) > (now or time.time()))
    except Exception:
        return False


def app_running(port=APP_PORT):
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def watchdog_once(config_path):
    """One pass: relaunch the app if a lock-in is on and it has been closed; end the job when the lock-in is over."""
    if not locked(config_path):
        remove()
        return 'removed'
    if app_running():
        return 'running'
    subprocess.Popen(app_command(), creationflags=0x00000008 | 0x08000000)  # detached, no console window
    return 'relaunched'
