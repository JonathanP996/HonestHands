"""Pulls text out of syllabus and assignment files, and finds the parts that matter."""
import html
import re
import zipfile
from pathlib import Path


def extract_text(path):
    p = Path(path).expanduser()
    if not p.exists():
        raise ValueError(f"Couldn't find {p.name}.")
    ext = p.suffix.lower()
    if ext == '.pdf':
        from Foundation import NSURL
        from Quartz import PDFDocument
        doc = PDFDocument.alloc().initWithURL_(NSURL.fileURLWithPath_(str(p)))
        if doc is None:
            raise ValueError("Couldn't open that PDF.")
        text = str(doc.string() or '')
    elif ext == '.docx':
        with zipfile.ZipFile(p) as z:
            xml = z.read('word/document.xml').decode('utf8', 'ignore')
        xml = re.sub(r'</w:p>', '\n', xml)
        xml = re.sub(r'<w:tab/>', '\t', xml)
        text = html.unescape(re.sub(r'<[^>]+>', '', xml))
    elif ext in ('.txt', '.md', '.tex', '.text', ''):
        text = p.read_text(errors='ignore')
    else:
        raise ValueError('That file type isn\'t supported. Use a PDF, Word (.docx), or text file, or paste the text.')
    if len(text.strip()) < 20:
        raise ValueError('No text found in that file. If it\'s a scanned PDF, copy the text and paste it instead.')
    return text


AI_TERMS = re.compile(r'\b(artificial intelligence|AI|A\.I\.|generative|ChatGPT|LLMs?|large language models?|chatbots?|Copilot|Claude|Gemini|GPT)\b', re.I)
OTHER_TERMS = re.compile(r'\b(collaborat\w*|plagiari\w*|academic (integrity|honesty|dishonesty|misconduct)|honor code|cheat\w*|outside (help|resources|sources)|cite|citation|LaTeX|formatting|online (tools|resources)|Chegg|Course ?Hero|Quizlet|Grammarly|Photomath|Wolfram|Stack ?Overflow|solutions? manual|unauthori[sz]ed|prohibit\w*|not (permitted|allowed)|tutors?|translat\w*|paraphras\w*|ghostwrit\w*|essay mills?)\b', re.I)


def relevant_sections(text, max_chars=7000):
    """Keeps sentences about AI and integrity (plus a little context), so the model reads less."""
    sentences = re.split(r'(?<=[.!?])\s+', re.sub(r'\s+', ' ', text))
    picked = set()
    for terms in (AI_TERMS, OTHER_TERMS):
        for i, s in enumerate(sentences):
            if terms.search(s):
                for j in range(max(0, i - 1), min(len(sentences), i + 3)):
                    picked.add(j)
            if sum(len(sentences[k]) for k in picked) > max_chars:
                break
    if not picked:
        return text[:max_chars]
    out, prev = [], -2
    for i in sorted(picked):
        if i != prev + 1:
            out.append('\n...\n')
        out.append(sentences[i] + ' ')
        prev = i
    return ''.join(out)[:max_chars]


def ai_policy_text(text, max_chars=12000):
    """The parts of a syllabus that govern AI and outside help, in original order, copied as written.
    Syllabi are short, so this keeps whole runs of sentences around each AI mention (and fills small
    gaps) rather than isolated lines. Nothing is paraphrased or dropped inside a run."""
    sentences = [x for x in re.split(r'(?<=[.!?])\s+|\n{2,}', re.sub(r'[ \t]+', ' ', text.replace('\r', ''))) if x.strip()]
    def pick(terms, before=1, after=2):
        keep = set()
        for i, sn in enumerate(sentences):
            if terms.search(sn):
                keep.update(range(max(0, i - before), min(len(sentences), i + after + 1)))
        # fill gaps of up to 3 unselected sentences between selected ones
        idx = sorted(keep)
        for a, b in zip(idx, idx[1:]):
            if 1 < b - a <= 4:
                keep.update(range(a, b))
        return keep
    keep = pick(AI_TERMS)
    keep |= pick(OTHER_TERMS, 1, 2)          # rules on outside help, collaboration and integrity also cover AI: never leave them out
    out, prev, total = [], -2, 0
    for i in sorted(keep):
        if total + len(sentences[i]) > max_chars:
            break
        out.append(('\n\n...\n\n' if i != prev + 1 and out else (' ' if out else '')) + sentences[i].strip())
        prev, total = i, total + len(sentences[i])
    return ''.join(out).strip()
