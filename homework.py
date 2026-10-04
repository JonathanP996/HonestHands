"""Finds which homework question (if any) a student's message looks like.

The assignment text is split into its questions and lettered parts once; each message is then compared against them with a
fast lexical match (milliseconds, no AI). The guard model is only consulted when something is close.
Intro rules and any appendix are left out: they aren't questions the student is asked to answer.
"""
import math
import re
from collections import Counter

STOP = set('the a an and or of to in is are for on with that this it as be by from at you your we our can will would should could how what '
           'why which when do does did have has not no yes if then than into about any all each more most some such use using used one two '
           'please give me my write show tell explain help want need let make get answer answers question questions problem problems following part parts '
           'note describe identify solve find compute calculate prove derive'.split())
HEADING = re.compile(r'^\s*(?:(?:q|question|problem|exercise)\s*\.?\s*\d+\b.*|\d{1,2}(?:\.\d{1,2})?\.?\s+\S.*\[\s*[\d.]+\s*(?:pts?|points?|%)[^\]]*\].*)$', re.I)
PART = re.compile(r'^\s*(?:\(?([a-h])[\.\)]|(\d{1,2})\.)\s+\S')
SECTION_NUM = re.compile(r'^\s*(?:q|question|problem|exercise)?\s*\.?\s*(\d{1,2})(?:\.(\d{1,2}))?', re.I)
APPENDIX = re.compile(r'^\s*(appendix|references|acknowledg)', re.I)
REF = re.compile(r'\b(?:q|question|problem|exercise|part)\s*\.?\s*(\d{1,2})\s*(?:\.\s*(\d{1,2}))?\s*(?:part\s*|\(|\s)?([a-h])?\b', re.I)


def _stem(w):
    for suf in ('ing', 'ed', 'es', 's'):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def toks(s):
    return [_stem(w) for w in re.findall(r"[a-z][a-z0-9']{2,}", s.lower()) if w not in STOP]


def words(s):
    return re.findall(r'[a-z0-9]+', s.lower())


def split_questions(text):
    """-> [{'label', 'num', 'part', 'text'}] for each question part, in order."""
    lines = [ln.rstrip() for ln in (text or '').replace('\r', '').split('\n')]
    sections, cur = [], None
    for ln in lines:
        if APPENDIX.match(ln) and sections:
            break
        if HEADING.match(ln):
            cur = {'heading': re.sub(r'\s*\[[^\]]*\]\s*', ' ', ln).strip(), 'num': (SECTION_NUM.match(ln) or [None, ''])[1] or '', 'sub': (SECTION_NUM.match(ln) or [None, None, None])[2], 'lines': []}
            sections.append(cur)
        elif cur is not None:
            cur['lines'].append(ln)
    def title(s):
        return re.sub(r'^(?:q|question|problem|exercise)?\s*\d+(?:\.\d+)*[:\.]?\s*', '', s['heading'].lower()).strip()
    best = {}
    for s in sections:
        k = title(s)
        if k not in best or len('\n'.join(s['lines'])) > len('\n'.join(best[k]['lines'])):
            best[k] = s
    sections = [s for s in sections if best.get(title(s)) is s]
    out = []
    for s in sections:
        body = '\n'.join(s['lines']).strip()
        if len(body) < 60:                          # a table-of-contents line, not a question
            continue
        parts, buf, letter = [], [], ''
        for ln in s['lines']:
            m = PART.match(ln)
            if m and buf and sum(len(b) for b in buf) > 40:
                parts.append((letter, ' '.join(buf))); buf = []
            if m:
                letter = (m.group(1) or m.group(2) or '')
            buf.append(ln.strip())
        if buf:
            parts.append((letter, ' '.join(buf)))
        num = s['num'] + (('.' + s['sub']) if s['sub'] else '')
        intro = ' '.join(s['lines'][:3])
        for letter, txt in parts if len(parts) > 1 else [('', ' '.join(s['lines']))]:
            txt = re.sub(r'\s+', ' ', txt).strip()
            if len(txt) < 40:
                continue
            label = f'{s["heading"]}' + (f' (part {letter})' if letter else '')
            out.append({'label': label, 'num': num, 'part': letter.lower() if letter.isalpha() else '', 'text': (s['heading'] + ': ' + txt)[:900]})
    if out:
        return out
    # no recognisable structure: fall back to overlapping windows over the paragraphs
    flat = re.sub(r'\s+', ' ', text or '')
    return [{'label': f'assignment text {i // 500 + 1}', 'num': '', 'part': '', 'text': flat[i:i + 700]} for i in range(0, max(len(flat) - 100, 1), 500)]


def build_index(text):
    chunks = split_questions(text)
    for c in chunks:
        c['toks'] = set(toks(c['text']))
        c['words'] = words(c['text'])
        c['grams'] = {tuple(c['words'][i:i + 8]) for i in range(max(len(c['words']) - 7, 0))}
    df = Counter(t for c in chunks for t in c['toks'])
    n = len(chunks)
    return {'chunks': chunks, 'idf': {t: math.log((n + 1) / (d + 0.5)) for t, d in df.items()}, 'n': n}


def find(message, index, k=2, min_cover=0.5):
    """Questions that the message copies, cites, or closely resembles. Each: {label, text, score, why}."""
    if not index or not index['chunks']:
        return []
    msg = message or ''
    mw = words(msg)
    hits = {}
    # 1) near word-for-word paste (8+ words in a row)
    mg = {tuple(mw[i:i + 8]) for i in range(max(len(mw) - 7, 0))}
    for i, c in enumerate(index['chunks']):
        if mg & c['grams']:
            hits[i] = {'score': 1.0, 'why': 'copied'}
    # 2) explicit citation: "question 3", "q2 part a", "problem 3b"
    for m in REF.finditer(msg.lower()):
        num, sub, part = m.group(1), m.group(2), m.group(3)
        want = num + (('.' + sub) if sub else '')
        for i, c in enumerate(index['chunks']):
            if c['num'] and (c['num'] == want or (not sub and c['num'].split('.')[0] == num)) and (not part or c['part'] == part):
                hits[i] = {'score': 1.5, 'why': 'cited'}
    # 3) topical resemblance: how much of the message's distinctive content shows up in the question
    mt = set(toks(msg))
    if len(mt) >= 2:
        idf = index['idf']
        total = sum(idf.get(t, 1.0) for t in mt) or 1.0
        rare = math.log((index['n'] + 1) / (max(2, 0.25 * index['n']) + 0.5))      # a word in few questions is "distinctive"
        for i, c in enumerate(index['chunks']):
            shared = mt & c['toks']
            if len([t for t in shared if idf.get(t, 0) >= rare]) < 2:
                continue
            cover = sum(idf.get(t, 1.0) for t in shared) / total
            if cover >= min_cover and i not in hits:
                hits[i] = {'score': round(cover, 2), 'why': 'similar'}
    ranked = sorted(hits.items(), key=lambda kv: -kv[1]['score'])[:k]
    return [{'label': index['chunks'][i]['label'], 'text': index['chunks'][i]['text'], **h} for i, h in ranked]
