"""The update check: offers a newer build, stays quiet for the same or older one, and remembers 'Later'."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import updates, version

class FakeStore:
    data = {'update_dismissed': 0}
    def save(self): pass

found = []
u = updates.Updater(FakeStore(), found.append)
def feed(build): updates.fetch = lambda: {'build': build, 'version': '9.9', 'notes': 'n', 'url': 'u'}
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); check.bad += 0 if ok else 1
check.bad = 0

feed(version.BUILD); u.check_now(); check(u.available() is None and not found, 'same build: nothing offered')
feed(version.BUILD - 1); u.check_now(); check(u.available() is None, 'older build: nothing offered')
feed(version.BUILD + 1); u.check_now(); check(u.available() and u.available()['build'] == version.BUILD + 1 and len(found) == 1, 'newer build: offered, announced once')
u.check_now(); check(len(found) == 1, 'checking again does not announce twice')
u.dismiss(); check(u.available() is None, 'Later hides that build')
feed(version.BUILD + 2); u.check_now(); check(u.available() and len(found) == 2, 'an even newer build comes back')
updates.fetch = lambda: None; u.check_now(); check(u.available() is not None, 'offline check keeps the last answer')
print('ALL PASSED' if not check.bad else 'FAILURES: %d' % check.bad)
sys.exit(1 if check.bad else 0)
