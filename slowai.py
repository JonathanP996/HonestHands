"""Never let a slow computer leave someone waiting on the AI.

Runs the AI check in a thread and waits a few seconds. If it has not answered, the keyword rules decide instead, so a message is
never held for long. Fast computers never notice: the AI answers well inside the wait. (SKIP_FOR can make a slow AI be skipped for a while.)"""
import threading
import time

import rules

WAIT = 20          # seconds to wait for the AI before the keyword rules decide
SKIP_FOR = 0       # 0 = every message gets the full wait; set e.g. 600 to skip a slow AI for ten minutes after two slow answers


def check_with_fallback(guard, fn, text, cls, asg, wait=WAIT):
    """fn() runs the real AI check. Returns its result, or a keyword-rules result tagged with why."""
    state = guard.__dict__.setdefault('_slow', {'strikes': 0, 'skip_until': 0.0})

    def keywords(why):
        r = dict(rules.check(text, cls, asg), source='keywords', note=why)
        r['verdict'] = 'allow' if r['level'] != 'flag' else 'warn'
        return r

    if SKIP_FOR and time.time() < state['skip_until']:
        return keywords('The AI is slow on this computer right now, so the keyword rules checked this.')
    box = {}

    def run():
        try:
            box['r'] = fn()
        except Exception as e:
            box['err'] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(wait)
    if 'r' in box:
        state['strikes'] = 0
        return box['r']
    state['strikes'] += 1
    if SKIP_FOR and state['strikes'] >= 2:
        state['skip_until'] = time.time() + SKIP_FOR
    return keywords(str(box.get('err') or 'The AI was slow, so the keyword rules checked this.'))
