"""Installs / removes the launchd job that runs watchdog.py during a timed lock-in (a per-user agent: no admin password)."""
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from store import APP_DIR

LABEL = 'app.honesthands.keepalive'


def plist_path(label=LABEL):
    return Path.home() / 'Library' / 'LaunchAgents' / f'{label}.plist'


def app_command():
    """How to start HonestHands again: the packaged app's own binary, or `python main.py` when run from source."""
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parent / 'main.py')]


def watcher_args(label=LABEL, config=None, lock=None, cmd=None, interval=3):
    cmd = cmd or app_command()
    base = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parent / 'main.py')]
    return base + ['--watchdog', '--config', str(config or APP_DIR / 'config.json'), '--lock', str(lock or APP_DIR / 'honesthands.lock'),
                   '--label', label, '--cmd', json.dumps(cmd), '--interval', str(interval)]


def install(label=LABEL, args=None):
    path = plist_path(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    plist = {'Label': label, 'ProgramArguments': args or watcher_args(label), 'KeepAlive': True, 'RunAtLoad': True,
             'ThrottleInterval': 5, 'EnvironmentVariables': {'PATH': os.environ.get('PATH', '/usr/bin:/bin')},
             'StandardOutPath': str(APP_DIR / 'keepalive.log'), 'StandardErrorPath': str(APP_DIR / 'keepalive.log')}
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], capture_output=True)   # replace any older copy
    with open(path, 'wb') as f:
        plistlib.dump(plist, f)
    r = subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(path)], capture_output=True, text=True)
    return r.returncode == 0


def remove(label=LABEL):
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], capture_output=True)
    try:
        plist_path(label).unlink()
    except OSError:
        pass


def loaded(label=LABEL):
    return subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{label}'], capture_output=True).returncode == 0
