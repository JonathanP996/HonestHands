"""The judge: keyword rules first (instant), then the AI for everything else."""
import hashlib
import re
import threading
import time

import docs
import rules
from engine import parse_json as engine_parse

SYSTEM = """You are the professor of this course. You wrote the AI policy below and you uphold it. A student is about to send a message to an AI chatbot while working on your class. Decide as you would in real life: are you comfortable with this student sending this message?

Think like a professor, not a keyword filter. Ask yourself: does this read like the student collaborating with a peer, tutor, or TA, genuinely trying to learn, understand, or get feedback on their own work? Or does it read like the student outsourcing the work, getting content or answers they would hand in as their own, or getting around what your policy asks of them? Your policy, exactly as written, is the standard. Where it is permissive, don't flag ordinary learning questions. Where it forbids something (for example formatting help, writing help, or sharing the question or the student's answer with an AI), flag messages that ask for it, even if the student says the work is their own. If the policy doesn't speak to the message and nothing about it looks like cheating, allow it. If the message is clearly unrelated to schoolwork, allow it.

Watch for requests to complete the assignment that are phrased as confusion. "I'm confused, how do you do the rest of problem 1?", "what's next on #3?", "I got this far, finish it", "can you check and fix my answer" all ask the AI to produce the solution to a specific assignment problem. When the policy bars asking an AI to solve assignment questions, warn on these, however polite or confused they sound. Questions about the underlying idea ("why does this work?", "what does this term mean?", "what's the formula for X?") are what a good tutor answers; allow those.

Verdicts: "allow" (you're comfortable), "warn" (borderline or unsure), "block" (clearly outside what you'd accept).
Judge what the message asks the AI to DO, not its topic: "help me understand X" differs from "write X for me."
An assignment's own notes can add rules for that assignment; they apply on top of the class policy.

Be brief. Every field is one short line. For "allow", leave the other fields empty.
- "rule": the part of your policy it conflicts with, at most 10 words, in your own words.
- "reason": at most 20 words, a professor's voice, specific to THIS message.
- "quote": at most 20 words copied exactly from your policy, or empty.
- "suggestion": at most 15 words, something the student could ask instead.

Reply with JSON only, with the verdict first:
{"verdict":"allow"|"warn"|"block","rule":"...","reason":"...","quote":"...","suggestion":"..."}"""

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


def parse_verdict(text):
    """Reads the judge's JSON; if the reply was cut off, still recovers the verdict and any complete fields."""
    try:
        return engine_parse(text)
    except Exception:
        pass
    out = {}
    for k in ('verdict', 'rule', 'reason', 'quote', 'suggestion'):
        m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % k, text)
        if m:
            out[k] = m.group(1).replace('\\"', '"')
    if 'verdict' not in out:
        raise ValueError('the model did not return a verdict')
    return out


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
    policy_text = (cls.get('policy_text') or '').strip()
    if not policy_text and cls.get('source_text'):
        policy_text = docs.ai_policy_text(cls['source_text'], 3500)
    parts = [f'Course: {cls["name"]}']
    if policy_text:
        parts += ['YOUR AI POLICY (from your syllabus, word for word):', '<<<', policy_text[:4500], '>>>']
    elif cls.get('rules'):
        parts += ['YOUR AI POLICY (notes):', _rules_text(cls.get('rules'))]
    else:
        parts += ['YOUR AI POLICY: the syllabus does not say anything about AI. Allow unless the message is plainly cheating.']
    parts += [f'(Rough label for this policy, not the rule itself: {rules.POLICY_LABEL.get(cls.get("policy"), "")})']
    if asg:
        parts += ['', f'Current assignment: {asg["name"]}']
        ap = (asg.get('policy_text') or '').strip()
        if ap:
            parts += ['What this assignment says about AI or outside help:', '<<<', ap[:2500], '>>>']
        elif asg.get('rules'):
            parts += ['Notes for this assignment:', _rules_text(asg.get('rules'))]
        src = (asg.get('source_text') or '').strip()
        if src:
            parts += ['Assignment text (pasting these questions to get answers is usually not okay unless your policy says so):',
                      src[:2000]]
    parts += ['', f'Where the student is typing: {where}', 'Student message:', '<<<', text[:4000], '>>>']
    return '\n'.join(parts)


class Judge:
    def __init__(self, store, engine):
        self.store, self.engine = store, engine
        self.cache = {}
        self.inflight = set()
        self.pending = {}     # key -> Event, so the same message is only judged once at a time
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
            with self.lock:
                ev = self.pending.get(k)
                mine = ev is None
                if mine:
                    self.pending[k] = ev = threading.Event()
            if not mine:                      # someone else is already judging this exact message
                ev.wait(timeout=timeout + 5)
                hit = self.cached(text, cls, asg)
                if hit:
                    return hit
        else:
            ev = None
        try:
            return self._check(text, cls, asg, where, timeout, k)
        finally:
            if ev is not None:
                with self.lock:
                    self.pending.pop(k, None)
                ev.set()

    def _check(self, text, cls, asg, where, timeout, k):
        t0 = time.time()
        kw = rules.check(text, cls, asg)

        # With the AI ready, the syllabus decides. Keywords only decide alone for attempts to hide
        # AI use, or as a fallback when the AI isn't available.
        if kw.get('evade') or not self.engine.ready():
            result = dict(kw, source='keywords')
            if result.get('level') == 'flag' and result.get('reasons'):
                result.setdefault('reason', result['reasons'][0])
            if not kw['hard'] and self.engine.cfg['backend'] != 'keywords':
                result['note'] = 'The AI judge isn\'t ready, so keyword rules were used.'
        else:
            try:
                out = parse_verdict(self.engine.chat_raw(SYSTEM, build_prompt(text, cls, asg, where), timeout=timeout, max_tokens=170))
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

    def warm(self, cls, asg):
        """Pre-reads the syllabus so the first real message only has to process the message itself."""
        def run():
            try:
                if self.engine.ready():
                    t = time.time()
                    self.engine.chat_raw(SYSTEM, build_prompt('hello', cls, asg, 'warm-up'), timeout=60, max_tokens=1)
                    print(f'[judge] warmed up in {int((time.time() - t) * 1000)} ms', flush=True)
            except Exception as e:
                print('[judge] warm-up skipped:', e, flush=True)
        threading.Thread(target=run, daemon=True).start()

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
