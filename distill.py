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


BROAD_BAN = re.compile(
    r"\bno\b[^.]{0,50}\b(ai|a\.i\.|artificial intelligence|chatgpt|generative|llms?)\b"
    r"|\b(ai|artificial intelligence|chatgpt|generative)\b[^.]{0,60}\b(not (be )?(allowed|permitted|used)|prohibit\w*|forbidden|banned|off[- ]limits)\b"
    r"|\b(do not|don't|may not|must not|cannot|never)\b[^.]{0,40}\b(use|using)\b[^.]{0,30}\b(ai|artificial intelligence|chatgpt)\b", re.I)


def pick_category(out, rule_list, fallback):
    """Turns the model's category answer into none/tutor/open without trusting exact wording."""
    raw = str(out.get('category') or out.get('policy') or '').strip().lower()
    reason = str(out.get('category_reason', ''))
    print('[distill] model category =', repr(raw), '| reason =', reason[:120], flush=True)
    cat = None
    if raw in rules.POLICY_LABEL:
        cat = raw
    elif re.search(r'\bnone\b|no ai|not allowed|prohibit|ban|forbid', raw):
        cat = 'none'
    elif 'tutor' in raw:
        cat = 'tutor'
    elif re.search(r'open|disclos|allowed|permit', raw):
        cat = 'open'
    # The bullets and the model's own reason are evidence too: a blanket ban in either wins
    # over a "tutor"/"open" label (or no label at all).
    ban_text = ' '.join(f"{r.get('rule', '')} {r.get('quote', '')}" for r in rule_list if r.get('type') == 'not_allowed')
    blanket = bool(BROAD_BAN.search(ban_text)) or bool(BROAD_BAN.search(reason))
    if cat in (None, 'tutor', 'open') and blanket:
        return 'none'
    return cat or fallback


CATEGORY_SYSTEM = """Below is the part of a course syllabus that governs students' use of AI tools. Give it a rough label and write a few sample messages.

Return JSON only:
{"category": "none" | "tutor" | "open",
 "category_reason": "one short sentence",
 "examples": [{"prompt": "a message a student might type to an AI chatbot for this class", "verdict": "allow" | "warn" | "block", "why": "short reason"}]}

category is only a rough label: "none" = no AI use at all; "tutor" = AI for explanations, hints, feedback and collaboration but not for producing the student's work; "open" = AI allowed, usually with disclosure or citation.
examples: 6 messages, 2 allow, 2 warn, 2 block, consistent with the policy."""


def analyze(engine, text, kind='class', name=''):
    text = (text or '').strip()
    if len(text) < 20:
        raise ValueError('That looks empty. If it\'s a scanned PDF, copy the text and paste it instead.')
    policy_guess, _ = rules.suggest_policy(text)
    policy_text = docs.ai_policy_text(text, 12000 if kind == 'class' else 8000)
    result = {'policy': policy_guess or 'tutor', 'rules': [], 'examples': [], 'dropped': 0, 'used_ai': False,
              'note': '', 'source_text': text[:(80000 if kind != 'class' else 40000)], 'policy_text': policy_text, 'category_reason': ''}
    if not policy_text:
        result['note'] = ('No mention of AI or outside help was found in this document. '
                          'Type or paste the rules into the box if there are any.')
        return result
    if kind == 'class' and engine.ready():
        try:
            out = engine.chat_json(CATEGORY_SYSTEM, f'Course: {name}\n\nSyllabus text:\n{policy_text}',
                                   timeout=120, max_tokens=900)
            result['policy'] = pick_category(out, [{'type': 'not_allowed', 'rule': policy_text, 'quote': ''}], result['policy'])
            result['category_reason'] = str(out.get('category_reason', '')).strip()
            for e in (out.get('examples') or [])[:8]:
                if isinstance(e, dict) and str(e.get('prompt', '')).strip():
                    v = str(e.get('verdict', 'warn')).lower()
                    result['examples'].append({'prompt': str(e['prompt']).strip(),
                                               'verdict': v if v in ('allow', 'warn', 'block') else 'warn',
                                               'why': str(e.get('why', '')).strip()})
            result['used_ai'] = True
        except Exception as e:
            result['note'] = f'The AI couldn\'t label this ({e}); the label is a keyword guess. The rules text is still exact.'
    elif kind == 'class':
        result['note'] = 'The AI guard isn\'t set up yet, so the label is a keyword guess. The rules text below is exact.'
    return result
