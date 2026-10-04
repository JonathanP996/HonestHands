"""The guard: checks a message against a class's AI policy.
Same rules as the browser extension, ported to Python. Runs 100% locally."""
import re

I = re.I
WORK = r'(essay|paper|paragraph|report|thesis|introduction|intro|conclusion|response|discussion post|reflection|article|story|poem|lab report|summary|outline|answers?|code|program|function|script|speech|analysis)'
TASK = r'(homework|assignment|problems?|questions?|worksheet|quiz|test|exam|lab|project|essay)'

GENERATE = [
    re.compile(rf'\b(write|draft|compose|create|generate|produce|make)\b.{{0,40}}\b{WORK}\b', I),
    re.compile(rf'\b(do|finish|complete|solve)\b.{{0,25}}\b(my|this|these|the)\b.{{0,25}}\b{TASK}\b', I),
    re.compile(r'\b(answer|solve)\s+(this|these|the following|all|each|every)\b', I),
    re.compile(r'\bwhat (is|are) the (correct )?(answer|answers|solution)s?\b', I),
    re.compile(r'\bgive me (the )?(final )?(answer|answers|solution|solutions)\b', I),
]
REWRITE = [re.compile(r'\b(paraphrase|reword|rephrase|rewrite|spin)\b', I)]
EVADE = [
    re.compile(r'\b(humani[sz]e|undetectable|bypass|avoid|evade|beat|pass|fool|trick)\b.{0,30}\b(ai[- ]?detect\w*|detectors?|turnitin|gptzero|zerogpt|plagiarism check\w*)', I),
    re.compile(r'\b(sound|look|seem|read)\s+(less\s+like\s+(an?\s+)?ai|more\s+human|like\s+a\s+(real\s+)?(student|human|person))', I),
    re.compile(r'\bnot\s+(sound|look|read)\s+like\s+(an?\s+)?(ai|chatgpt|a bot)', I),
]
LEARNING = re.compile(r'\b(explain|why|how (does|do|did|is|are|can)|help me understand|what does|quiz me|check my|feedback|hint|walk me through|example of|difference between|am i right)\b', I)

POLICY_LABEL = {
    'none': 'No AI allowed',
    'tutor': 'Tutor only',
    'open': 'AI allowed, with disclosure',
}
TIPS = {
    'none': "Try your notes, the textbook, office hours, or your school's tutoring or writing center instead.",
    'tutor': 'Try: "Explain [concept] so I can write it myself," "Give me a hint, not the answer," or "Here\'s my draft. What\'s unclear?"',
    'open': 'Keep a record of how you used AI so you can disclose it.',
}


def _any(patterns, text):
    return any(p.search(text) for p in patterns)


def _words(t):
    return set(re.findall(r'[a-z]{5,}', t.lower()))


def _overlap(prompt, desc):
    d = _words(desc)
    if len(d) < 8:
        return 0.0
    return len(d & _words(prompt)) / len(d)


def check(prompt, cls, asg=None):
    """Returns {'level': 'ok'|'note'|'flag', 'hard': bool, 'reasons': [...], 'tip': str}"""
    reasons, flagged, hard = [], False, False
    evade = _any(EVADE, prompt)
    policy = cls.get('policy', 'tutor')

    if evade:
        flagged = hard = True
        reasons.append('This looks like an attempt to hide AI use or get past a detector. That is blocked under every policy.')

    if policy == 'none':
        flagged = hard = True
        reasons.append(f"The syllabus for {cls['name']} doesn't allow AI use.")
    elif policy == 'tutor':
        if _any(GENERATE, prompt):
            flagged = True
            reasons.append('This asks the AI to produce the work or the answers. This class only allows AI as a tutor: explanations, hints, and feedback.')
        if _any(REWRITE, prompt) and len(prompt) > 200:
            flagged = True
            reasons.append('Having AI rewrite or paraphrase text usually counts as AI-generated work in a tutor-only class.')
        asg_text = (asg or {}).get('source_text') or (asg or {}).get('desc') or ''
        if asg_text and _overlap(prompt, asg_text) > 0.5:
            flagged = True
            reasons.append(f'It looks like you pasted the instructions for "{asg["name"]}". Ask about one concept instead of handing over the whole task.')
        if not flagged and len(prompt) > 1500 and not LEARNING.search(prompt):
            flagged = True
            reasons.append("That's a big paste with no question about understanding it. Make sure you're asking for feedback, not for the AI to do the work.")

    if flagged:
        return {'level': 'flag', 'hard': hard, 'evade': evade, 'reasons': reasons, 'tip': TIPS.get(policy, TIPS['tutor'])}
    if policy == 'open' and (_any(GENERATE, prompt) or _any(REWRITE, prompt)):
        return {'level': 'note', 'hard': False, 'evade': False, 'reasons': ['AI is allowed in this class. Remember to disclose how you used it.'], 'tip': ''}
    return {'level': 'ok', 'hard': False, 'evade': False, 'reasons': [], 'tip': ''}


AI_MENTION = re.compile(r'\b(AI|A\.I\.|ChatGPT|generative|artificial intelligence|chatbots?|large language models?|LLMs?|Claude|Gemini|Copilot)\b', I)


def suggest_policy(text):
    """Finds the AI-policy sentences in a syllabus and guesses the policy."""
    sentences = re.split(r'(?<=[.!?])\s+', re.sub(r'\s+', ' ', text))
    ai = [s for s in sentences if AI_MENTION.search(s)]
    if not ai:
        return None, []
    j = ' '.join(ai)
    banned = re.search(r'\b(prohibit\w*|not (be )?(permitted|allowed)|forbidden|banned|may not|must not|cannot|can ?not|not be used|no use of|zero tolerance)\b', j, I)
    allowed = re.search(r'\b(permitted|allowed|encouraged|may use|welcome|acceptable)\b', j, I)
    disclose = re.search(r'\b(cite|citation|disclose|acknowledg\w*|document)\b', j, I)
    tutorish = re.search(r'\b(brainstorm\w*|feedback|tutor\w*|explain\w*|study aid|understand\w*)\b', j, I)
    blanket = re.search(r'\bno\b[^.]{0,50}\b(ai|a\.i\.|artificial intelligence|chatgpt|generative|llms?)\b', j, I)
    policy = 'tutor'
    if banned or blanket:
        policy = 'none'
    if allowed and disclose and not banned:
        policy = 'open'
    if tutorish and allowed:
        policy = 'tutor'
    return policy, ai[:5]
