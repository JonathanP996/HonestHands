"""Where everything is saved: classes, rules, the current session, settings, and the log."""
import json
import threading
import uuid
from pathlib import Path

APP_DIR = Path.home() / 'Library' / 'Application Support' / 'HonestHands'
CONFIG = APP_DIR / 'config.json'
LOG = APP_DIR / 'log.jsonl'

DEFAULTS = {
    'classes': [],
    'session': None,
    'mode': 'warn',
    'pin': '',
    'engine': {'backend': 'builtin', 'model': 'small', 'ollama_model': 'qwen2.5:3b'},
    'onboarded': False,
}


def new_id():
    return uuid.uuid4().hex[:8]


class Store:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.data = self._load()

    def _load(self):
        data = json.loads(json.dumps(DEFAULTS))
        if CONFIG.exists():
            try:
                saved = json.loads(CONFIG.read_text())
            except Exception:
                saved = {}
            for k in DEFAULTS:
                if k in saved:
                    data[k] = saved[k]
            data['engine'] = dict(DEFAULTS['engine'], **saved.get('engine', {}))
        return data

    def save(self):
        with self.lock:
            tmp = CONFIG.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data, indent=2))
            tmp.replace(CONFIG)

    def cls(self, cid):
        return next((c for c in self.data['classes'] if c['id'] == cid), None)

    @staticmethod
    def asg(cls, aid):
        if not cls or not aid:
            return None
        return next((a for a in cls.get('assignments', []) if a['id'] == aid), None)

    def session_targets(self):
        s = self.data.get('session')
        if not s:
            return None, None
        c = self.cls(s.get('class_id'))
        return c, self.asg(c, s.get('assignment_id'))

    def log(self, entry):
        with self.lock, LOG.open('a') as f:
            f.write(json.dumps(entry) + '\n')

    def read_log(self, limit=None):
        if not LOG.exists():
            return []
        lines = LOG.read_text().splitlines()
        if limit:
            lines = lines[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out

    def clear_log(self):
        with self.lock:
            LOG.write_text('')
