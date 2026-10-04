"""Platform-neutral warning overlay. The UI lives in a separate helper process that
speaks the JSON-lines protocol in overlay/PROTOCOL.md, so a Windows build only needs to
supply its own helper and a backend here. Falls back (returns False) if no helper exists."""
import json
import os
import subprocess
import sys
import threading


class OverlayBackend:
    """Interface every platform backend implements."""
    def available(self): return False
    def show(self, payload, on_choice): raise NotImplementedError
    def hide(self): pass
    def close(self): pass


class SubprocessOverlay(OverlayBackend):
    """Runs a helper executable and relays show/choice messages over stdin/stdout."""
    def __init__(self, exe):
        self.exe, self.proc = exe, None
        self._cbs, self._lock, self._n = {}, threading.Lock(), 0

    def available(self):
        return bool(self.exe) and os.access(self.exe, os.X_OK)

    def _ensure(self):
        if self.proc and self.proc.poll() is None:
            return True
        try:
            self.proc = subprocess.Popen([self.exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         text=True, bufsize=1)
        except OSError as e:
            print('overlay helper failed to start:', e)
            return False
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        return True

    def _read(self, proc):
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get('event') == 'choice':
                with self._lock:
                    cb = self._cbs.pop(msg.get('id'), None)
                if cb:
                    cb(msg.get('choice', 'edit'))
        # Helper died: release anything still waiting so the keyboard never stays held.
        with self._lock:
            pending, self._cbs = list(self._cbs.values()), {}
        for cb in pending:
            cb('edit')

    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + '\n')
        self.proc.stdin.flush()

    def show(self, payload, on_choice):
        if not self._ensure():
            return False
        with self._lock:
            self._n += 1
            bid = str(self._n)
            self._cbs[bid] = on_choice
        try:
            self._send(dict(payload, cmd='show', id=bid))
            return True
        except (OSError, ValueError):
            with self._lock:
                self._cbs.pop(bid, None)
            return False

    def is_open(self):
        with self._lock:
            return bool(self._cbs) and self.proc is not None and self.proc.poll() is None

    def owns_point(self, x, y):
        """True if (x, y) in global screen coordinates is over the helper's window."""
        try:
            from Quartz import (CGWindowListCopyWindowInfo, kCGNullWindowID,
                                kCGWindowListOptionOnScreenOnly)
            for w in CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []:
                if w.get('kCGWindowOwnerPID') != self.proc.pid:
                    continue
                b = w['kCGWindowBounds']
                if b['X'] <= x <= b['X'] + b['Width'] and b['Y'] <= y <= b['Y'] + b['Height']:
                    return True
        except Exception:
            pass
        return False

    def choose(self, choice):
        try:
            self._send({'cmd': 'choose', 'choice': choice})
        except Exception:
            pass

    def checking(self):
        try:
            if self._ensure():
                self._send({'cmd': 'checking'})
        except Exception:
            pass

    def hide(self):
        try:
            self._send({'cmd': 'hide'})
        except Exception:
            pass

    def close(self):
        try:
            self._send({'cmd': 'quit'})
        except Exception:
            pass


def _helper_path():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    for p in (os.path.join(base, 'overlay', 'bin', 'HHOverlay'),
              os.path.join(base, 'overlay', 'mac', '.build', 'release', 'HHOverlay')):
        if os.path.exists(p):
            return p
    return None


def create_backend():
    if sys.platform == 'darwin':
        b = SubprocessOverlay(_helper_path())
        if b.available():
            return b
    # Windows: return SubprocessOverlay(path to a Windows helper) here.
    return None
