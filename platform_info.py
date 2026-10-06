"""Which computer is this? Everything that differs between Mac and Windows asks here, so the shared code stays shared."""
import sys

IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform.startswith('win')
NAME = 'mac' if IS_MAC else 'windows' if IS_WIN else 'other'


import os
import subprocess


def open_path(path, reveal=False):
    """Open a file or folder in Finder / File Explorer (reveal=True highlights it inside its parent folder)."""
    path = str(path)
    if IS_WIN:
        if reveal:
            subprocess.Popen(['explorer', '/select,', path])
        else:
            os.startfile(path)
    else:
        subprocess.Popen(['open', '-R', path] if reveal else ['open', path])


def open_settings(page):
    """page: 'notifications'."""
    if IS_WIN:
        os.startfile('ms-settings:notifications')
    else:
        subprocess.Popen(['open', 'x-apple.systempreferences:com.apple.Notifications-Settings.extension'])


def open_in_browser(info, url=''):
    """Open a browser (info is an entry of browsers.BROWSERS), on url if given."""
    if IS_WIN:
        exe = info.get('winexe') or ''
        subprocess.Popen(['cmd', '/c', 'start', '', exe] + ([url] if url else []), shell=False)
    else:
        subprocess.Popen(['open', '-b', info['bundle']] + ([url] if url else []))
