"""The judge: keyword rules first (instant), then the AI for everything else."""
import hashlib
import threading
import time

import rules

SYSTEM = """You check a message a student is about to send to an AI chatbot while doing schoolwork, against that class's and assignment's rules.

Verdicts:
- "allow": the message follows the rules. Asking the AI to explain a concept, give an example of an idea, give a hint, or give feedback on the student's OWN work is usually fine when the class allows AI as a tutor.
- "warn": the message might break a rule, or you are not sure.
- "block": the message clearly breaks a rule, such as asking the AI to produce graded work, give answers to assignment questions, or do something a rule specifically forbids (for example formatting or LaTeX, if a rule forbids that).

Judge what the message asks the AI to DO, not its topic. "How do I…" is different from "do it for me."
Assignment rules override class rules, but "assignment rules override class rules" is NOT itself a rule — never report that as the rule.

When you warn or block, be specific and personal:
- "reason": one sentence saying what THIS message is asking for, naming the actual thing (e.g. "This asks Gemini to convert your answer into LaTeX formatting.").
- "rule": the specific rule from the list that it breaks, in plain words (e.g. "No AI for formatting or LaTeX"). Use a real rule from the lists, not a generic phrase. Empty only if nothing specific applies.
- "quote": the exact words from the rule list's quotes that back this up, copied verbatim, or empty if there is none.
- "suggestion": one short, concrete alternative the student could ask instead, specific to what they wanted.

Reply with JSON only:
{"verdict":"allow"|"warn"|"block","reason":"...","rule":"...","quote":"...","suggestion":"..."}"""

LABELS = {'allowed': 'ALLOWED', 'not_allowed': 'NOT ALLOWED', 'condition': 'CONDITION', 'exception': 'EXCEPTION'}

STARTER_TESTS = {
    'tutor': [
        ('Can you explain how gradient descent works in simple terms?', 'allow'),
        ('Why might my training loss go up after a few epochs?', 'allow'),
        ('Give me a hint for how to start this kind of problem, without solving it.', 'allow'),
        ("What's the difference between precision and recall?", 'allow'),
        ('Write the full solution to this homework problem for me.', 'block'),
        ("Here's question 3 from my homework, just give me the final answer.", 'block'),
        ("Rewrite my essay so it doesn't sound like AI wrote it.", 'block'),
        ('Complete this function for my assignment so it passes the tests.', 'block'),
    ],
}


def _rules_text(items):
    if not items:
        return '(none listed)'
    out = []
    for r in items or []:
        line = f'- {LABELS.get(r.get("type"), "RULE")}: {r.get("rule", "")}'
        q = (r.get('quote') or '').strip()
        if q:
            line += f'  [from syllabus: "{q}"]'
        out.append(line)
    return '\n'.join(out)


def build_prompt(text, cls, asg, where):
    parts = [f'Class: {cls["name"]}',
             f'Overall AI policy: {rules.POLICY_LABEL.get(cls.get("policy"), "")}',
             'Class rules:', _rules_text(cls.get('rules'))]
    if asg:
        parts += ['', f'Current assignment: {asg["name"]}', 'Assignment rules:', _rules_text(asg.get('rules'))]
        src = (asg.get('source_text') or '').strip()
        if src:
            parts += ['Assignment text (pasting these questions to get answers is not allowed under tutor-only rules):',
                      src[:2000]]
    examples = (cls.get('examples') or []) + ((asg or {}).get('examples') or [])
    if examples:
        parts += ['', 'Examples for this class:']
        parts += [f'- "{e["prompt"]}" -> {e["verdict"]}' + (f' ({e["why"]})' if e.get('why') else '')
                  for e in examples[:10]]
    parts += ['', f'Where the student is typing: {where}', 'Student message:', '<<<', text[:4000], '>>>']
    return '\n'.join(parts)


class Judge:
    def __init__(self, store, engine):
        self.store, self.engine = store, engine
        self.cache = {}
        self.inflight = set()
        self.lock = threading.Lock()

    @staticmethod
    def key(text, cls, asg):
        return (cls['id'], asg['id'] if asg else '', hashlib.sha1(text.strip().encode()).hexdigest())

    def cached(self, text, cls, asg):
        with self.lock:
            return self.cache.get(self.key(text, cls, asg))

    def forget(self):
        with self.lock:
            self.cache.clear()

    def check(self, text, cls, asg, where='', timeout=12, use_cache=True):
        k = self.key(text, cls, asg)
        if use_cache:
            hit = self.cached(text, cls, asg)
            if hit:
                return hit
        t0 = time.time()
        kw = rules.check(text, cls, asg)

        if kw['hard'] or not self.engine.ready():
            result = dict(kw, source='keywords')
            if result.get('level') == 'flag' and result.get('reasons'):
                result.setdefault('reason', result['reasons'][0])
            if not kw['hard'] and self.engine.cfg['backend'] != 'keywords':
                result['note'] = 'The AI judge isn\'t ready, so keyword rules were used.'
        else:
            try:
                out = self.engine.chat_json(SYSTEM, build_prompt(text, cls, asg, where), timeout=timeout, max_tokens=120)
                v = str(out.get('verdict', '')).strip().lower()
                if v not in ('allow', 'warn', 'block'):
                    raise ValueError('unexpected verdict')
                reason = str(out.get('reason', '')).strip()
                rule = str(out.get('rule', '')).strip()
                quote = str(out.get('quote', '')).strip()
                suggestion = str(out.get('suggestion', '')).strip()
                if v == 'allow':
                    note = kw['level'] == 'note'
                    result = {'level': 'note' if note else 'ok', 'hard': False,
                              'reasons': kw['reasons'] if note else ([reason] if reason else []), 'tip': ''}
                else:
                    result = {'level': 'flag', 'hard': False,
                              'reason': reason or 'This looks like it breaks a rule for this class.',
                              'rule': rule, 'quote': quote,
                              'tip': suggestion or rules.TIPS.get(cls.get('policy'), rules.TIPS['tutor'])}
                    # reasons[] stays as a plain fallback for the log and older views
                    result['reasons'] = [result['reason']] + ([f'Rule: {rule}'] if rule else [])
                result['verdict'] = v
                result['source'] = 'ai'
            except Exception as e:
                result = dict(kw, source='keywords', note=f'The AI judge didn\'t answer ({e}), so keyword rules were used.')

        if 'verdict' not in result:
            result['verdict'] = 'allow' if result['level'] != 'flag' else ('block' if result['hard'] else 'warn')
        result['ms'] = int((time.time() - t0) * 1000)
        if result['source'] == 'ai' or result['hard']:
            with self.lock:
                self.cache[k] = result
                if len(self.cache) > 300:
                    self.cache.pop(next(iter(self.cache)))
        return result

    def prejudge(self, text, cls, asg, where):
        """Checks a draft in the background while you type, so sending feels instant."""
        k = self.key(text, cls, asg)
        with self.lock:
            if k in self.cache or k in self.inflight:
                return
            self.inflight.add(k)

        def run():
            try:
                self.check(text, cls, asg, where, timeout=20)
            finally:
                with self.lock:
                    self.inflight.discard(k)
        threading.Thread(target=run, daemon=True).start()

    def accuracy_test(self, cls, asg):
        tests = [(e['prompt'], e['verdict']) for e in (cls.get('examples') or []) + ((asg or {}).get('examples') or [])]
        tests += STARTER_TESTS.get(cls.get('policy'), [])
        results = []
        for prompt, expected in tests:
            r = self.check(prompt, cls, asg, 'Accuracy test', timeout=30, use_cache=False)
            got = r['verdict']
            passed = (expected == 'allow') == (got == 'allow')
            results.append({'prompt': prompt, 'expected': expected, 'got': got, 'pass': passed,
                            'ms': r['ms'], 'source': r['source']})
        n = len(results)
        return {
            'results': results,
            'accuracy': round(100 * sum(r['pass'] for r in results) / n) if n else 0,
            'avg_ms': int(sum(r['ms'] for r in results) / n) if n else 0,
            'used_ai': any(r['source'] == 'ai' for r in results),
        }
