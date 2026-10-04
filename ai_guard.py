"""The guard: keyword rules first (instant), then the AI for everything else."""
import hashlib
import re
import threading
import time

import distill
import docs
import homework
import ocr
import rules
from engine import parse_json as engine_parse

SYSTEM = """You are the professor of this course. You wrote the AI policy below and you uphold it. A student is about to send a message to an AI chatbot while working on your class. Decide as you would in real life: are you comfortable with this student sending this message?

Think like a professor, not a keyword filter. Ask yourself: does this read like the student collaborating with a peer, tutor, or TA, genuinely trying to learn, understand, or get feedback on their own work? Or does it read like the student outsourcing the work, getting content or answers they would hand in as their own, or getting around what your policy asks of them? Your policy, exactly as written, is the standard. Where it is permissive, don't flag ordinary learning questions. Where it forbids something (for example formatting help, writing help, or sharing the question or the student's answer with an AI), flag messages that ask for it, even if the student says the work is their own. If the policy doesn't speak to the message and nothing about it looks like cheating, allow it. If the message is clearly unrelated to schoolwork, allow it.

Watch for requests to complete the assignment that are phrased as confusion. "I'm confused, how do you do the rest of problem 1?", "what's next on #3?", "I got this far, finish it", "can you check and fix my answer" all ask the AI to produce the solution to a specific assignment problem. When the policy bars asking an AI to solve assignment questions, warn on these, however polite or confused they sound. Questions about the underlying idea ("why does this work?", "what does this term mean?", "what's the formula for X?") are what a good tutor answers; allow those.

Verdicts: "allow" (you're comfortable), "warn" (borderline or unsure), "block" (clearly outside what you'd accept).
Weigh what the message asks the AI to DO, not its topic: "help me understand X" differs from "write X for me."
An assignment's own notes can add rules for that assignment; they apply on top of the class policy.

Work through it in this order, in the JSON fields:
1. "asks": what the student wants the AI to do, starting with "Asks the AI to" (at most 15 words).
2. "policy_says": the sentence of YOUR policy that covers that, copied exactly (at most 25 words), or "none" if nothing in the policy speaks to it.
3. "forbidden": true if that sentence forbids or restricts what the student asks (for example formatting help, writing help, sharing the question, asking for the answer), otherwise false. If the policy says a kind of help is not permitted, then asking for that help is forbidden, even when the student says the work is their own.
4. "verdict": "allow", "warn" or "block". If forbidden is true the verdict is "warn" or "block"; if it is false the verdict is usually "allow".
5. "rule": the part of your policy involved, at most 10 words, in your own words ("" if none).
6. "suggestion": at most 15 words, something the student could ask instead ("" for allow).

Reply with JSON only, in exactly this order:
{"asks":"...","policy_says":"...","forbidden":true|false,"verdict":"allow"|"warn"|"block","rule":"...","suggestion":"..."}"""

EXTRACT_SYSTEM = """You read a course's AI policy and turn it into two short checklists.

1. "forbidden": the kinds of REQUESTS a student is not allowed to make to an AI chatbot under this policy. One item per distinct restriction. Write each item as an action starting with a verb, for example "ask the AI to solve a homework question", "use AI to fix or format LaTeX in your own answer", "share the assignment question, or your own answer or work, with the AI (even just to check or fix it)". Include the policy's own restrictions about formatting, writing, rewriting, sharing questions or work, and getting answers or solutions, whenever the policy states them. For each item give "quote": the exact words from the policy that forbid it (at most 25 words, copied exactly).
2. "allowed": the kinds of requests the policy explicitly allows, as short actions (for example "ask about topics and formulae", "ask what a LaTeX command does").

Never list something as forbidden if the policy says it IS allowed or fine (for example, a policy may allow copying your own work into your own conversation, or asking general questions). Only include what the policy actually says. At most 8 forbidden and 5 allowed items.
Reply with JSON only: {"forbidden":[{"item":"...","quote":"..."}],"allowed":["..."]}"""

CLASSIFY_SYSTEM = """You screen one message a student is about to send to an AI chatbot, for one course. Below is a numbered list of requests this course's AI policy FORBIDS, and a list of requests it ALLOWS.

Decide whether the message asks the AI for any forbidden request. Match on what the student wants the AI to DO, not on the topic, and ignore typos and slang. Asking to understand an idea, a formula or a command in general terms is not the same as asking the AI to work on the student's own answer or assignment problem. Pasting or describing the student's own answer, work, or an assignment question in the message counts as sharing it. Only match an item if the message really asks for it. If it matches none, answer 0.

How to match, with unrelated examples (a cooking class whose forbidden list is: 1. ask the AI to write your recipe for you  2. share your own dish description with the AI  3. use AI to translate your recipe card):
- "make up a recipe for lemon bars for my assignment" -> {"match": 1, "suggestion": "Ask what makes lemon bars set, then write the recipe yourself."}
- "here's my dish, is the plating okay?" -> {"match": 2, "suggestion": "Ask a general question about plating, without describing your dish."}
- "put my recipe card into Spanish" -> {"match": 3, "suggestion": "Ask what a Spanish cooking term means."}
- "why does bread need to rise?" -> {"match": 0, "suggestion": ""}
A reworded or shortened request still matches: what counts is the action the student wants done, not the exact words.

Reply with JSON only: {"match": <number of the forbidden item, or 0>, "suggestion": "<at most 15 words the student could ask instead, or empty if match is 0>"}"""

VERIFY_SYSTEM = """You check one claim about a course's AI policy. Read the policy, then decide what it says about the action described.
Reply with JSON only: {"policy": "forbids" | "allows" | "silent"}
"forbids" = the policy says students must not do this. "allows" = the policy says students may do this, or that it is fine. "silent" = the policy does not say."""

RELATED_SYSTEM = """A course bans AI use entirely, including for anything the student does for the course. Decide whether the student's message is about this course's subject (for example studying, practising, translating, vocabulary, grammar, homework, or explanations of the course material) as opposed to something unrelated (cooking, travel, general chat).
Reply with JSON only: {"related": true|false}"""

HOMEWORK_SYSTEM = """You help check a student's message to an AI chatbot against the homework they are working on. Below are the homework questions that look closest to the message.

Answer copies=true if the message asks the AI to do what one of these homework questions asks the student to do: solve it, prove it, derive it, compute it, write it out, or finish it. That still counts when the message is reworded, shortened, partial, or has small changes.
Answer copies=false if the message only asks what something means, how an idea or algorithm works in general, or for background that the question does not itself ask the student to produce.

Reply with JSON only: {"copies": true|false, "which": "<letter of the question, or empty>"}"""

HW_ITEM = re.compile(r"\b(question|problem|solve|answer|solution|homework|assignment|share)\w*", re.I)

PERMISSION = re.compile(r"^\W*(?:you|students?)\s+(?:can|may|are welcome to|are free to)\s+(?!not\b|never\b)|^\W*feel free|^\W*it is (?:fine|okay|ok|appropriate) to", re.I)

BAN_HINT = re.compile(r"\b(not (be )?(permitted|allowed)|prohibit\w*|forbid\w*|may not|must not|cannot|never|dishonest\w*)\b", re.I)

CONTRADICTS = re.compile(r"\b(prohibit\w*|forbid\w*|not (be )?(permitted|allowed|okay|appropriate)|isn'?t (permitted|allowed)|"
                         r"violat\w*|dishonest\w*|against (the |your )?(policy|rules)|inappropriate|conflicts? with)\b", re.I)

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
    """Reads the guard's JSON; if the reply was cut off, still recovers the verdict and any complete fields."""
    try:
        return engine_parse(text)
    except Exception:
        pass
    out = {}
    for k in ('asks', 'policy_says', 'verdict', 'rule', 'reason', 'quote', 'suggestion'):
        m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % k, text)
        if m:
            out[k] = m.group(1).replace('\\"', '"')
    m = re.search(r'"forbidden"\s*:\s*(true|false)', text, re.I)
    if m:
        out['forbidden'] = m.group(1).lower() == 'true'
    if 'verdict' not in out and 'forbidden' not in out:
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


class AIGuard:
    def __init__(self, store, engine):
        self.store, self.engine = store, engine
        self.cache = {}
        self.inflight = set()
        self.items = {}           # (class, assignment, policy hash) -> checklist
        self.hw_index = {}        # (assignment, text hash) -> its questions, ready to search
        self.items_pending = {}
        self.items_failed = {}
        self.pending = {}     # key -> Event, so the same message is only guarded once at a time
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
            if not mine:                      # someone else is already guarding this exact message
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

    def _freeform(self, text, cls, asg, where, timeout, kw):
        """The whole policy goes to the model with every message (used when no checklist is available)."""
        out = parse_verdict(self.engine.chat_raw(SYSTEM, build_prompt(text, cls, asg, where), timeout=timeout, max_tokens=260))
        forbidden = out.get('forbidden')
        forbidden = forbidden if isinstance(forbidden, bool) else str(forbidden).strip().lower() in ('true', 'yes')
        v = str(out.get('verdict', '')).strip().lower()
        if v not in ('allow', 'warn', 'block'):
            if 'forbidden' not in out:
                raise ValueError('unexpected verdict')
            v = 'warn' if forbidden else 'allow'     # the model skipped the verdict but answered the key question
        reason = str(out.get('asks') or out.get('reason') or '').strip()
        rule = str(out.get('rule', '')).strip()
        quote = '' if str(out.get('policy_says', out.get('quote', ''))).strip().lower() in ('none', '') else str(out.get('policy_says', out.get('quote', ''))).strip()
        suggestion = str(out.get('suggestion', '')).strip()
        # A model that says "forbidden" (or whose own words say so) can't also say "allow".
        if v == 'allow' and (forbidden or CONTRADICTS.search(reason)):
            v = 'warn'
        if v != 'allow' and not reason:
            reason = 'This looks like it breaks a rule for this class.'
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
        return result

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
                result['note'] = 'The AI guard isn\'t ready, so keyword rules were used.'
        else:
            try:
                items = self.items_for(cls, asg, wait=min(timeout, 12))
                hw = self._homework_check(text, cls, asg, where, timeout, items) if (asg and items) else None
                if hw:
                    result = hw                          # it matches one of this assignment's own questions
                elif items:
                    result = self._classify_result(text, cls, asg, where, timeout, items, kw)
                else:
                    result = self._freeform(text, cls, asg, where, timeout, kw)
            except Exception as e:
                result = dict(kw, source='keywords', note=f'The AI guard didn\'t answer ({e}), so keyword rules were used.')

        if 'verdict' not in result:
            result['verdict'] = 'allow' if result['level'] != 'flag' else ('block' if result['hard'] else 'warn')
        result['ms'] = int((time.time() - t0) * 1000)
        if result['source'] == 'ai' or result['hard']:
            with self.lock:
                self.cache[k] = result
                if len(self.cache) > 300:
                    self.cache.pop(next(iter(self.cache)))
        return result

    def _policy_parts(self, cls, asg):
        cp = (cls.get('policy_text') or '').strip()
        if not cp and cls.get('source_text'):
            cp = docs.ai_policy_text(cls['source_text'], 3500)
        return cp, ((asg or {}).get('policy_text') or '').strip()

    def items_for(self, cls, asg, wait=12):
        """The private checklist (forbidden / allowed requests) for this class + assignment, built once per policy text."""
        cp, ap = self._policy_parts(cls, asg)
        if not (cp or ap):
            return None
        key = (cls['id'], (asg or {}).get('id', ''), hashlib.sha1((cp + '||' + ap).encode()).hexdigest()[:16])
        with self.lock:
            if key in self.items:
                return self.items[key]
            if time.time() - self.items_failed.get(key, 0) < 90:
                return None                       # it failed recently; use the full-policy check for now
            ev = self.items_pending.get(key)
            mine = ev is None
            if mine:
                self.items_pending[key] = ev = threading.Event()
        if not mine:
            ev.wait(timeout=wait)
            with self.lock:
                return self.items.get(key)
        try:
            items = self._extract_items(cls, asg, cp, ap)
            with self.lock:
                if items:
                    self.items[key] = items
                else:
                    self.items_failed[key] = time.time()
            return items
        except Exception as e:
            print('[guard] could not build the checklist:', e, flush=True)
            with self.lock:
                self.items_failed[key] = time.time()
            return None
        finally:
            with self.lock:
                self.items_pending.pop(key, None)
            ev.set()

    def _extract_items(self, cls, asg, cp, ap):
        user = f'Course: {cls["name"]}\n\nCLASS AI POLICY:\n{cp or "(none)"}'
        if ap:
            user += f'\n\nASSIGNMENT ({asg["name"]}) AI NOTES:\n{ap}'
        data = engine_parse(self.engine.chat_raw(EXTRACT_SYSTEM, user, timeout=120, max_tokens=900))
        src = distill.norm(cp + ' ' + ap)
        forbidden = []
        for it in (data.get('forbidden') or [])[:10]:
            if not isinstance(it, dict):
                continue
            item, quote = str(it.get('item', '')).strip(), str(it.get('quote', '')).strip()
            item = re.sub(r'\s*\bverbatim\b', '', item)                  # sharing counts even when it isn't word for word
            if item:
                forbidden.append({'item': item, 'quote': quote if quote and distill.quote_is_real(quote, src) else ''})
        allowed = [str(a).strip() for a in (data.get('allowed') or [])[:6] if str(a).strip()]
        # Second look: drop anything the policy actually allows (small models sometimes list the allowed half of a sentence).
        policy = f'{cp}\n\n{ap}'.strip()
        kept = []
        for f in forbidden:
            try:
                raw = self.engine.chat_raw(VERIFY_SYSTEM, f'POLICY:\n{policy}\n\nACTION: {f["item"]}', timeout=60, max_tokens=24)
                m = re.search(r'"policy"\s*:\s*"(\w+)"', raw)
                if m and m.group(1).lower() == 'allows':
                    print(f'[guard] dropped checklist item the policy allows: {f["item"]}', flush=True)
                    continue
            except Exception:
                pass
            kept.append(f)
        forbidden = [f for f in kept if not (f['quote'] and PERMISSION.search(f['quote']))]   # "You can copy your own work…" is a permission
        if not forbidden and BAN_HINT.search(cp + ' ' + ap):
            return None            # the policy clearly forbids something but we found nothing: don't trust an empty list
        print(f'[guard] checklist for {cls["name"]}{" / " + asg["name"] if asg else ""}: '
              f'{len(forbidden)} forbidden, {len(allowed)} allowed', flush=True)
        return {'forbidden': forbidden, 'allowed': allowed}

    def _hw_index(self, asg):
        src = (asg or {}).get('source_text') or ''
        if len(src) < 200:
            return None
        key = (asg['id'], hashlib.sha1(src.encode()).hexdigest()[:12])
        with self.lock:
            idx = self.hw_index.get(key)
        if idx is None:
            idx = homework.build_index(src)
            with self.lock:
                self.hw_index[key] = idx
        return idx

    def _homework_check(self, text, cls, asg, where, timeout, items=None):
        """Does this message copy, cite, or closely resemble one of THIS assignment's questions? None = no concern."""
        if not asg:
            return None
        items = items or self.items_for(cls, asg, wait=1)
        gate = [f for f in (items or {}).get('forbidden', []) if HW_ITEM.search(f['item'])]
        if not gate:
            return None                               # this policy doesn't forbid asking the AI about assignment questions
        idx = self._hw_index(asg)
        cands = homework.find(text, idx) if idx else []
        if not cands:
            return None
        why = cands[0]['why']
        if why == 'similar' or why == 'cited':
            letters = 'ABCDE'
            body = '\n'.join(f'[{letters[i]}] {c["label"]}: {c["text"][:600]}' for i, c in enumerate(cands))
            raw = self.engine.chat_raw(HOMEWORK_SYSTEM, f'Closest homework questions:\n{body}\n\nStudent message:\n<<<\n{text[:1500]}\n>>>', timeout=timeout, max_tokens=40)
            if not re.search(r'"copies"\s*:\s*true', raw, re.I):
                return None
            m = re.search(r'"which"\s*:\s*"?([A-E])', raw)
            c = cands[letters.index(m.group(1))] if m else cands[0]
        else:
            c = cands[0]                              # a near word-for-word paste needs no second opinion
        where_q = c['label']
        f = gate[0]
        reason = f'This looks like it comes from the assignment ({where_q}). Asking the AI to solve it isn\'t allowed.'
        res = {'level': 'flag', 'hard': False, 'reason': reason, 'rule': "Don't ask the AI to solve assignment questions", 'quote': f['quote'],
               'tip': 'Ask about the idea behind it instead, without pasting the question. For example, "What does this term mean?" or "How does this method work in general?"',
               'verdict': 'warn', 'source': 'ai'}
        res['reasons'] = [reason, f'Rule: {res["rule"]}']
        return res

    def _classify_prompt(self, text, cls, items, where):
        lst = '\n'.join(f'{i + 1}. {f["item"]}' for i, f in enumerate(items['forbidden'])) or '(none)'
        al = '\n'.join(f'- {a}' for a in items['allowed']) or '(none listed)'
        ban = ''
        if cls.get('policy') == 'none':
            ban = ('This course bans AI use entirely, including for anything the student does for the course. A message that asks the AI '
                   'for help with this course\'s material (language, homework, practice, translation, explanations) matches: give the number '
                   'of the closest forbidden item. A message unrelated to the course does not match.\n\n')
        return (f'Course: {cls["name"]}\n{ban}Forbidden requests:\n{lst}\n\nAllowed requests:\n{al}\n\n'
                f'Where the student is typing: {where}\nStudent message:\n<<<\n{text[:3000]}\n>>>')

    def _classify_result(self, text, cls, asg, where, timeout, items, kw):
        raw = self.engine.chat_raw(CLASSIFY_SYSTEM, self._classify_prompt(text, cls, items, where), timeout=timeout, max_tokens=90)
        m = re.search(r'"match"\s*:\s*"?(\d+)', raw)
        if not m:
            raise ValueError('the model did not say which item matched')
        n = int(m.group(1))
        if (n <= 0 or n > len(items['forbidden'])) and cls.get('policy') == 'none' and items['forbidden']:
            # A class that bans AI outright: anything about the course counts, even if no specific item names it.
            rel = self.engine.chat_raw(RELATED_SYSTEM, f'Course: {cls["name"]}\nStudent message:\n<<<\n{text[:2000]}\n>>>', timeout=timeout, max_tokens=20)
            if re.search(r'"related"\s*:\s*true', rel, re.I):
                f = items['forbidden'][0]
                res = {'level': 'flag', 'hard': False, 'reason': 'This class doesn\'t allow AI for anything you do for it.',
                       'rule': 'No AI for this class', 'quote': f['quote'], 'tip': rules.TIPS['none'], 'verdict': 'warn', 'source': 'ai'}
                res['reasons'] = [res['reason'], 'Rule: No AI for this class']
                return res
        if n <= 0 or n > len(items['forbidden']):
            note = kw['level'] == 'note'
            return {'level': 'note' if note else 'ok', 'hard': False, 'reasons': kw['reasons'] if note else [], 'tip': '',
                    'verdict': 'allow', 'source': 'ai'}
        f = items['forbidden'][n - 1]
        s = re.search(r'"suggestion"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        reason = 'This asks the AI to ' + (f['item'][:1].lower() + f['item'][1:]).rstrip('.') + '.'
        res = {'level': 'flag', 'hard': False, 'reason': reason, 'rule': f['item'], 'quote': f['quote'],
               'tip': (s.group(1).strip() if s and s.group(1).strip() else rules.TIPS.get(cls.get('policy'), rules.TIPS['tutor'])),
               'verdict': 'warn', 'source': 'ai'}
        res['reasons'] = [reason, f'Rule: {f["item"]}']
        return res

    def warm(self, cls, asg):
        """Pre-reads the syllabus so the first real message only has to process the message itself."""
        def run():
            try:
                if self.engine.ready():
                    t = time.time()
                    items = self.items_for(cls, asg, wait=120)
                    if items:
                        self.engine.chat_raw(CLASSIFY_SYSTEM, self._classify_prompt('hello', cls, items, 'warm-up'), timeout=60, max_tokens=1)
                    else:
                        self.engine.chat_raw(SYSTEM, build_prompt('hello', cls, asg, 'warm-up'), timeout=60, max_tokens=1)
                    print(f'[guard] warmed up in {int((time.time() - t) * 1000)} ms', flush=True)
            except Exception as e:
                print('[guard] warm-up skipped:', e, flush=True)
        threading.Thread(target=run, daemon=True).start()

    def check_with_images(self, text, images, cls, asg, where='', timeout=12, n_images=0, use_cache=True):
        """Like check(), for a message with pictures attached. The pictures are read on this Mac (Apple Vision) and treated as
        typed text, so "do this" + a screenshot of a homework question is judged by what the screenshot says."""
        t0 = time.time()
        text = (text or '').strip()
        n = max(len(images or []), n_images or 0)
        read = [ocr.read_text(i) for i in (images or [])[:3]]
        blob = '\n'.join(t for t in read if t).strip()

        def tag(r):
            r = dict(r)
            r['picture'] = True
            r['ms'] = int((time.time() - t0) * 1000)
            if r.get('verdict') != 'allow' and r.get('reason'):
                rs = r['reason']
                if rs.startswith('This looks like it comes from'):
                    r['reason'] = 'The picture you attached ' + rs[len('This '):]
                elif text and len(text) > 12:
                    r['reason'] = 'With the picture you attached, ' + rs[:1].lower() + rs[1:]
                elif rs.startswith('This '):
                    r['reason'] = 'The picture you attached ' + rs[len('This '):]
                r['reasons'] = [r['reason']] + [x for x in (r.get('reasons') or [])[1:]]
            return r

        if len(blob) >= 20:                                            # readable: judge it like typed text
            combined = (text + '\n\n' if text else '') + '[Text read from the attached picture]\n' + blob
            return tag(self.check(combined, cls, asg, where, timeout=timeout, use_cache=use_cache))
        # a picture with no readable text (a photo, handwriting, a diagram): we can't see what it holds
        base = self.check(text, cls, asg, where, timeout=timeout, use_cache=use_cache) if text else None
        items = self.items_for(cls, asg, wait=min(timeout, 12))
        gate = [f for f in (items or {}).get('forbidden', []) if HW_ITEM.search(f['item'])]
        if base and base.get('verdict') != 'allow' and (len(text) > 12 or not gate):
            return tag(base)                              # the typed message is a problem on its own
        if gate:
            reason = ("You attached a picture the guard can't read. This policy doesn't allow sharing assignment questions or your work "
                      "with an AI, and a picture is an easy way around that.")
            res = {'level': 'flag', 'hard': False, 'reason': reason, 'rule': "Don't share assignment questions or your work with the AI",
                   'quote': gate[0]['quote'], 'tip': 'Type your own question about the idea, without attaching the assignment or your answer.',
                   'verdict': 'warn', 'source': 'ai', 'reasons': [reason]}
            return tag(res)
        return tag(base or {'level': 'ok', 'hard': False, 'reasons': [], 'tip': '', 'verdict': 'allow', 'source': 'ai'})

    def preguard(self, text, cls, asg, where):
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
