"""A picture next to a message: what the student asks for decides it, unless the class bans putting the question itself into an AI.
Stand-in AI, runs anywhere."""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import store
store.APP_DIR = Path(tempfile.mkdtemp())
import ai_guard

BLOB = 'Problem 3a. Show that the loss is convex. ' * 3                 # readable text in the picture


class Eng:
    def ready(self):
        return True

    def chat_raw(self, system, user, timeout=0, max_tokens=0):
        if system.startswith('A student attached a picture'):
            asked = user.lower()
            return '{"does_work": false}' if re.search(r'convert|latex|format|typeset|proofread', asked) else '{"does_work": true}'
        return '{}'


class G(ai_guard.AIGuard):
    def __init__(self, items):
        super().__init__(type('S', (), {'data': {}})(), Eng())
        self._items = items
        self.seen = []

    def items_for(self, cls, asg, wait=0):
        return self._items

    def check(self, text, cls, asg, where='', timeout=12, use_cache=True):
        self.seen.append(text)
        bad = re.search(r'solve|answer', text, re.I) or 'Text read from the attached picture' in text
        if bad:
            return {'level': 'flag', 'hard': False, 'reason': 'This asks the AI to solve it.', 'rule': 'r', 'quote': 'q', 'tip': 't', 'verdict': 'warn', 'source': 'ai', 'reasons': ['x']}
        return {'level': 'ok', 'hard': False, 'reasons': [], 'tip': '', 'verdict': 'allow', 'source': 'ai'}


ai_guard.ocr.read_text = lambda img: BLOB
solve_only = {'forbidden': [{'item': 'ask the AI to solve a homework problem', 'quote': 'Do not use AI to solve problems.'}], 'allowed': []}
share_ban = {'forbidden': [{'item': 'paste or upload a picture of the homework question into the AI', 'quote': 'Never paste a question or a picture of it into an AI.'}], 'allowed': []}
cls = {'id': 'c', 'name': 'ML', 'policy': 'tutor'}

g = G(solve_only)
r = g.check_with_images('convert my finished handwritten work to latex', ['img'], cls, None)
assert r['verdict'] == 'allow', r                                       # allowed request on finished work, no ban on the question itself
r = g.check_with_images('solve this', ['img'], cls, None)
assert r['verdict'] == 'warn', r                                        # asks for the work
r = G(share_ban).check_with_images('convert my finished handwritten work to latex', ['img'], cls, None)
assert r['verdict'] == 'warn' and r.get('picture'), r                   # this class bans the question/picture itself
ai_guard.ocr.read_text = lambda img: ''                                 # unreadable handwriting
assert G(solve_only).check_with_images('convert this to latex', ['img'], cls, None)['verdict'] == 'allow'
assert G(solve_only).check_with_images('solve this', ['img'], cls, None)['verdict'] == 'warn'
assert G(share_ban).check_with_images('convert this to latex', ['img'], cls, None)['verdict'] == 'warn'
print('picture intent: ok')
