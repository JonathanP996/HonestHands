"""Reads a syllabus or assignment once and turns it into a short, checked rule list."""
import difflib
import re

import docs
import rules

CLASS_SYSTEM = """You read a course syllabus and pull out the rules about students using AI tools (ChatGPT, Claude, Gemini, Copilot, and similar) and closely related rules about collaboration and outside help.

Return JSON only, in this shape:
{"policy": "none" | "tutor" | "open",
 "rules": [{"type": "allowed" | "not_allowed" | "condition" | "exception", "rule": "short plain-English rule", "quote": "the exact sentence from the text this rule comes from"}],
 "examples": [{"prompt": "a message a student might type to an AI chatbot for this class", "verdict": "allow" | "warn" | "block", "why": "short reason"}]}

policy: "none" = no AI use allowed; "tutor" = AI only for explanations, hints, feedback; "open" = AI allowed with disclosure.
Copy every quote word for word from the text. Only include rules the text actually states. At most 10 rules.
Give 6 examples: 2 allow, 2 warn, 2 block, specific to this course's subject."""

ASG_SYSTEM = """You read one assignment for a course and pull out any rules about using AI tools or outside help that apply to THIS assignment only.

Return JSON only, in this shape:
{"rules": [{"type": "allowed" | "not_allowed" | "condition" | "exception", "rule": "short plain-English rule", "quote": "the exact sentence from the text this rule comes from"}],
 "examples": [{"prompt": "a message a student might type to an AI chatbot while doing this assignment", "verdict": "allow" | "warn" | "block", "why": "short reason"}]}

Copy every quote word for word. If the assignment says nothing about AI or outside help, return an empty rules list.
Give 4 examples about this assignment's actual content: 2 allow (asking to understand concepts) and 2 block (asking for the answers or the work itself)."""

TYPES = {'allowed', 'not_allowed', 'condition', 'exception'}


def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def quote_is_real(quote, source_norm):
    q = norm(quote)
    if len(q) < 12:
        return False
    if q in source_norm:
        return True
    sm = difflib.SequenceMatcher(None, q, source_norm, autojunk=False)
    m = sm.find_longest_match(0, len(q), 0, len(source_norm))
    return m.size >= 0.85 * len(q)


def guess_type(sentence):
    if re.search(r'\b(not|never|prohibit\w*|forbid\w*|may not|must not|cannot|dishonest\w*)\b', sentence, re.I):
        return 'not_allowed'
    if re.search(r'\b(cite|disclose|acknowledg\w*)\b', sentence, re.I):
        return 'condition'
    return 'allowed'


def analyze(engine, text, kind='class', name=''):
    text = (text or '').strip()
    if len(text) < 20:
        raise ValueError('That looks empty. If it\'s a scanned PDF, copy the text and paste it instead.')
    policy_guess, evidence = rules.suggest_policy(text)
    result = {'policy': policy_guess or 'tutor', 'rules': [], 'examples': [], 'dropped': 0,
              'used_ai': False, 'note': '', 'source_text': text[:20000]}

    if engine.ready():
        try:
            if kind == 'class':
                body = f'Course: {name}\n\nRelevant parts of the syllabus:\n{docs.relevant_sections(text)}'
                out = engine.chat_json(CLASS_SYSTEM, body, timeout=300, max_tokens=1600)
            else:
                body = f'Assignment: {name}\n\n{text[:7000]}'
                out = engine.chat_json(ASG_SYSTEM, body, timeout=300, max_tokens=1200)
            src = norm(text)
            for r in (out.get('rules') or [])[:12]:
                if not isinstance(r, dict):
                    continue
                rule, quote = str(r.get('rule', '')).strip(), str(r.get('quote', '')).strip()
                if not rule:
                    continue
                if quote_is_real(quote, src):
                    t = r.get('type') if r.get('type') in TYPES else guess_type(quote)
                    result['rules'].append({'type': t, 'rule': rule, 'quote': quote})
                else:
                    result['dropped'] += 1
            for e in (out.get('examples') or [])[:8]:
                if isinstance(e, dict) and str(e.get('prompt', '')).strip():
                    v = str(e.get('verdict', 'warn')).lower()
                    result['examples'].append({'prompt': str(e['prompt']).strip(),
                                               'verdict': v if v in ('allow', 'warn', 'block') else 'warn',
                                               'why': str(e.get('why', '')).strip()})
            if kind == 'class' and out.get('policy') in rules.POLICY_LABEL:
                result['policy'] = out['policy']
            result['used_ai'] = True
            if result['dropped']:
                result['note'] = (f'{result["dropped"]} rule(s) were removed because their quote couldn\'t be found '
                                  'in your document. Add anything important that\'s missing.')
        except Exception as e:
            result['note'] = f'The AI couldn\'t finish reading it ({e}). These rules come from a keyword search instead.'
    else:
        result['note'] = ('The AI judge isn\'t set up yet, so these rules come from a keyword search. '
                          'Set up the AI judge in Settings, then use "Re-read document" for better rules.')

    if not result['rules'] and kind == 'class':
        for s in evidence:
            result['rules'].append({'type': guess_type(s), 'rule': s.strip(), 'quote': s.strip()})
    return result
