"""Is there a newer HonestHands? Looks at the website's version.json now and then; the app shows a banner if so."""
import json
import os
import sys
import threading
import time
import urllib.request

import net
import version

CHECK_EVERY = 3600


def enabled():
    return bool(getattr(sys, 'frozen', False)) or os.environ.get('HH_CHECK_UPDATES') == '1'     # not when run from source


def fetch():
    """The latest published build as {'build', 'version', 'notes', 'url'}, or None if it can't be reached."""
    try:
        from platform_info import IS_WIN
        name = 'version-windows.json' if IS_WIN else 'version.json'          # each system has its own newest build
        default = '/HonestHands-Setup.exe' if IS_WIN else '/HonestHands.dmg'
        req = urllib.request.Request(version.SITE + '/' + name + '?t=%d' % time.time(), headers={'User-Agent': 'HonestHands/%s' % version.VERSION})
        with urllib.request.urlopen(req, timeout=10, context=net.context()) as r:
            d = json.loads(r.read().decode())
        return {'build': int(d['build']), 'version': str(d.get('version') or ''), 'notes': str(d.get('notes') or ''),
                'url': str(d.get('url') or version.SITE + default)}
    except Exception:
        return None


def newer(latest):
    return bool(latest) and latest['build'] > version.BUILD


class Updater:
    def __init__(self, store, on_new):
        self.store, self.on_new = store, on_new
        self.latest = None

    def available(self):
        """The newer build to offer, unless this exact one was dismissed."""
        if newer(self.latest) and self.latest['build'] != self.store.data.get('update_dismissed', 0):
            return self.latest
        return None

    def check_now(self):
        latest = fetch()
        if latest:
            was = self.latest['build'] if self.latest else 0
            self.latest = latest
            if newer(latest) and latest['build'] != was:
                self.on_new(latest)
        return self.available()

    def start(self):
        if not enabled():
            return
        def loop():
            time.sleep(8)
            while True:
                self.check_now()
                time.sleep(CHECK_EVERY)
        threading.Thread(target=loop, daemon=True).start()

    def dismiss(self):
        if self.latest:
            self.store.data['update_dismissed'] = self.latest['build']
            self.store.save()
