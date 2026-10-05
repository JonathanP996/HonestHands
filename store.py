"""Where everything is saved: classes, rules, the current session, settings, and the log."""
import json
import os
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
    'engine': {'backend': 'builtin', 'model': 'small'},
    'onboarded': False,
    'cloud': {},
    'lock': {'browsers': True, 'ai_apps': False},   # what to turn you back from while a session is on
    'theme': 'system',      # system | light | dark
    'browser': '',          # chrome | edge | firefox | safari | '' (not chosen yet)
}


TUTOR_ID = '__tutor__'
TUTOR_POLICY = """AI-Based Assistance
Treat your AI source like a human source, with all accompanying plagiarism implications.

We treat AI-based assistance, such as ChatGPT and Copilot, the same way we treat collaboration with other people: you are welcome to talk about your ideas and work with other people, both inside and outside the class, as well as with AI-based assistants.

However, all work you submit must be your own. You should never include in your assignment anything that was not written directly by you without proper citation (including quotation marks and in-line citation for direct quotes).

Including anything you did not write in your assignment without proper citation will be treated as an academic misconduct case. If you are unsure where the line is between collaborating with AI and copying AI, we recommend the following heuristics:

Heuristic 1: Never hit "Copy" within your conversation with an AI assistant. You can copy your own work into your own conversation, but do not copy anything from the conversation back into your assignment. Instead, use your interaction with the AI assistant as a learning experience, then let your assignment reflect your improved understanding.

Heuristic 2: Do not have your assignment and the AI agent open at the same time. Use your conversation with the AI as a learning experience, then close the interaction down, open your assignment, and let your assignment reflect your revised knowledge. This heuristic includes avoiding using AI directly integrated into your composition environment: just as you should not let a classmate write content or code directly into your submission, so also you should avoid using tools that directly add content to your submission.

Deviating from these heuristics does not automatically qualify as academic misconduct; however, following these heuristics essentially guarantees your collaboration will not cross the line into misconduct."""
COLORS = ['orchid', 'olive', 'lav', 'mint', 'sun', 'sky', 'rose', 'peach', 'sage', 'sand']
TUTOR_CLASS = {'id': TUTOR_ID, 'name': 'Tutor mode', 'policy': 'tutor', 'color': 'ink', 'policy_text': TUTOR_POLICY,
               'rules': [], 'examples': [], 'assignments': [], 'builtin': True}


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
            data['engine'] = dict(DEFAULTS['engine'])           # one built-in model; older choices are ignored
        return data

    def save(self):
        with self.lock:
            tmp = CONFIG.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data, indent=2))
            tmp.replace(CONFIG)
            try:
                os.chmod(CONFIG, 0o600)       # holds the cloud sign-in token
            except OSError:
                pass

    def cls(self, cid):
        if cid == TUTOR_ID:
            return TUTOR_CLASS
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
