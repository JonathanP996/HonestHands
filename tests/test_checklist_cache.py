"""The checklist is built once, saved to disk, reused after a 'restart', and anything the first pass missed is added by the second.
Uses a stand-in for the AI, so it runs anywhere and fast."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import store
store.APP_DIR = Path(tempfile.mkdtemp())            # never touch the real saved checklists
import ai_guard

POLICY = ("Students may not use AI to solve homework problems. Students may not use AI to write any part of the lab report. "
          "You must cite any AI you use for brainstorming. You can ask AI to explain a concept.")


class FakeEngine:
    def __init__(self):
        self.calls = []

    def ready(self):
        return True

    def chat_raw(self, system, user, timeout=0, max_tokens=0):
        self.calls.append(system[:30])
        if system.startswith('You read a course'):          # the first pass misses the lab report rule
            return json.dumps({'forbidden': [{'item': 'ask the AI to solve a homework problem', 'quote': 'Students may not use AI to solve homework problems.'}],
                               'allowed': ['ask AI to explain a concept']})
        if system.startswith('You check a checklist'):      # the second pass finds it, plus a repeat and one invented rule
            return json.dumps({'forbidden': [
                {'item': 'use the AI to write any part of the lab report', 'quote': 'Students may not use AI to write any part of the lab report.'},
                {'item': 'ask the AI to solve a homework problem for you', 'quote': 'Students may not use AI to solve homework problems.'},   # a repeat
                {'item': 'use AI during exams', 'quote': 'No AI is allowed during exams.'}]})                                                        # not in the policy
        return '{"policy": "forbids"}'


class FakeStore:
    data = {'classes': [], 'session': None}


cls = {'id': 'c1', 'name': 'Chem', 'policy_text': POLICY, 'assignments': []}
eng = FakeEngine()
g = ai_guard.AIGuard(FakeStore(), eng)
items = g.items_for(cls, None)
names = [f['item'] for f in items['forbidden']]
assert len(names) == 2, names                                  # homework + lab report; the repeat and the invented rule are out
assert any('lab report' in n for n in names), names
assert not any('exams' in n for n in names), names
n_calls = len(eng.calls)
assert (store.APP_DIR / 'checklists.json').exists()

# "restart": a brand new guard with the same saved file must not call the AI at all
eng2 = FakeEngine()
g2 = ai_guard.AIGuard(FakeStore(), eng2)
again = g2.items_for(cls, None)
assert again == items and eng2.calls == [], eng2.calls

# a changed policy is re-read; an assignment without its own notes shares the class checklist
cls2 = dict(cls, policy_text=POLICY + ' No AI on quizzes.')
eng3 = FakeEngine()
ai_guard.AIGuard(FakeStore(), eng3).items_for(cls2, None)
assert eng3.calls, 'a changed policy must be re-read'
eng4 = FakeEngine()
ai_guard.AIGuard(FakeStore(), eng4).items_for(cls, {'id': 'a1', 'name': 'HW1'})
assert eng4.calls == [], 'same policy, no assignment notes: reuse'
print('checklist cache: ok  (first build used %d AI calls, a restart used 0)' % n_calls)
