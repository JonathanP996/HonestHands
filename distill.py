"""Reads a syllabus or assignment once and turns it into a short, checked rule list."""
import difflib
import re

import docs
import rules

CLASS_SYSTEM = """You are reading a course syllabus to work out exactly what the instructor says about students using AI tools (ChatGPT, Claude, Gemini, Copilot, and similar), plus closely related rules about collaboration, outside help, and tools.

Return JSON only, in this shape:
{"ai_policy_excerpt": ["a passage copied word for word from the text", "..."],
 "rules": [{"type": "not_allowed" | "allowed" | "condition" | "exception", "rule": "specific plain-English bullet", "quote": "the exact sentence from the text this bullet comes from"}],
 "category": "none" | "tutor" | "open",
 "category_reason": "one sentence explaining why",
 "examples": [{"prompt": "a message a student might type to an AI chatbot for this class", "verdict": "allow" | "warn" | "block", "why": "short reason"}]}

ai_policy_excerpt: every passage of the syllabus that deals with AI, collaboration, or outside help, copied exactly. Keep it short; skip unrelated text.
rules: a bullet for each distinct thing the syllabus says. List what is NOT okay first. Be specific: name the tools, the kinds of tasks (e.g. writing, translating, formatting, code, brainstorming), the conditions (e.g. "must disclose and cite"), and the exceptions (e.g. a named app that IS allowed). Use the instructor's own meaning; don't invent rules and don't generalize beyond the text. At most 14 bullets.
category: only a rough label. "none" = no AI use at all; "tutor" = AI only for explanations, hints, feedback; "open" = AI allowed (usually with disclosure). Decide it from the bullets you wrote.
Copy every quote and excerpt word for word. If the text says nothing about AI or outside help, return empty lists.
examples: 6 examples specific to this course's subject: 2 allow, 2 warn, 2 block, consistent with your bullets."""

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
              'used_ai': False, 'note': '', 'source_text': text[:20000], 'policy_text': '', 'category_reason': ''}

    if engine.ready():
        try:
            if kind == 'class':
                # Syllabi are short: read the whole thing when it fits, otherwise the AI/integrity parts.
                if len(text) <= 16000:
                    body = f'Course: {name}\n\nFull syllabus:\n{text}'
                else:
                    body = f'Course: {name}\n\nRelevant parts of the syllabus:\n{docs.relevant_sections(text, 12000)}'
                out = engine.chat_json(CLASS_SYSTEM, body, timeout=300, max_tokens=2400)
            else:
                body = f'Assignment: {name}\n\n{text[:7000]}'
                out = engine.chat_json(ASG_SYSTEM, body, timeout=300, max_tokens=1200)
            src = norm(text)
            for r in (out.get('rules') or [])[:14]:
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
            if kind == 'class':
                cat = out.get('category') or out.get('policy')
                if cat in rules.POLICY_LABEL:
                    result['policy'] = cat
                result['category_reason'] = str(out.get('category_reason', '')).strip()
                ex = out.get('ai_policy_excerpt') or []
                ex = [ex] if isinstance(ex, str) else ex
                good = [str(p).strip() for p in ex if quote_is_real(str(p), src)]
                result['policy_text'] = '\n\n'.join(good)[:3500]
            result['used_ai'] = True
            if result['dropped']:
                result['note'] = (f'{result["dropped"]} rule(s) were removed because their quote couldn\'t be found '
                                  'in your document. Add anything important that\'s missing.')
        except Exception as e:
            result['note'] = f'The AI couldn\'t finish reading it ({e}). These rules come from a keyword search instead.'
    else:
        result['note'] = ('The AI judge isn\'t set up yet, so these rules come from a keyword search. '
                          'Set up the AI judge in Settings, then use "Re-read document" for better rules.')

    if kind == 'class' and not result['policy_text']:
        # AI gave no verifiable passage (or isn't ready): use the sentences that mention AI.
        result['policy_text'] = ' '.join(s.strip() for s in evidence)[:3500]
    if not result['rules'] and kind == 'class':
        for s in evidence:
            result['rules'].append({'type': guess_type(s), 'rule': s.strip(), 'quote': s.strip()})
    return result
