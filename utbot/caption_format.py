"""Lossless formatting repair for AI-produced internal editorial captions.

Publication appends the verified photo credit and the five hashtags separately.
This function may change layout and move trailing tags out of the prose but may
not write new factual statements, turn assertions into questions, or invent a
photo credit. Semantic problems still require a fresh editorial rewrite/QC.
"""
import re


QUESTION_START = re.compile(
    r'(?i)^(?:apa(?:kah)?|mengapa|kenapa|bagaimana|siapa|kapan|di\s+mana|'
    r'ke\s+mana|dari\s+mana|seberapa|berapa|mungkinkah|akankah)\b'
)
TAG_LINE = re.compile(r'^\s*(?:#[A-Za-z0-9_]+\s*){1,8}$')
CREDIT_LINE = re.compile(r'(?i)^\s*(?:photo\s+by|foto\s+oleh)\s*:\s*.+$')


def normalize_generated_caption(value):
    """Return (content-only caption, separated footer hashtags, repair codes).

    The only punctuation edit permitted is turning an explicitly interrogative
    final sentence's trailing full stop into a question mark.
    """
    if not isinstance(value, str):
        return value, [], []
    original = value
    text = value.replace('\r\n', '\n').replace('\r', '\n').strip()
    repairs = []
    if text.startswith('&#'):
        # Never interpret escaped HTML as markup, or delete it.
        pass
    text = re.sub(r'(?i)^\s*(?:\*\*)?caption(?:\*\*)?\s*:\s*', '', text).strip()
    if text != original.strip():
        repairs.append('removed_caption_label')
    lines = text.split('\n')
    removed_tags = []
    # Hashtags/credit appended by the model belong to a different publishing
    # layer. Remove only terminal, standalone footer lines.
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if TAG_LINE.fullmatch(last):
            removed_tags = re.findall(r'#[A-Za-z0-9_]+', last) + removed_tags
            lines.pop()
            repairs.append('separated_footer_hashtags')
            continue
        if CREDIT_LINE.fullmatch(last):
            lines.pop()
            repairs.append('separated_photo_credit')
            continue
        break
    text = '\n'.join(lines).strip()
    text = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', text)

    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if not (4 <= len(paragraphs) <= 5):
        # Some models separate full editorial paragraphs with single newlines.
        candidate = [line.strip() for line in text.split('\n') if line.strip()]
        if 4 <= len(candidate) <= 5 and all(
            len(line) >= 20 and re.search(r'[.!?]["”]?\s*$', line)
            for line in candidate
        ):
            paragraphs = candidate
            text = '\n\n'.join(candidate)
            repairs.append('restored_paragraph_separators')
        elif len(paragraphs) == 1:
            # Safe only for exactly 4-5 complete sentences. No paraphrase.
            sentences = [part.strip() for part in re.split(
                r'(?<=[.!?])\s+(?=[A-ZÀ-Þ“"])', text
            ) if part.strip()]
            if 4 <= len(sentences) <= 5 and all(
                re.search(r'[.!?]["”]?\s*$', sentence) for sentence in sentences
            ):
                paragraphs = sentences
                text = '\n\n'.join(sentences)
                repairs.append('restored_sentence_paragraphs')
    # Fix punctuation only if the closing sentence is clearly a question.
    if paragraphs and paragraphs[-1].endswith('.') and QUESTION_START.match(
        paragraphs[-1].strip().lstrip('"“')
    ):
        text = text.rstrip()[:-1] + '?'
        repairs.append('question_punctuation')
    return text, removed_tags, repairs


class DraftFormatError(ValueError):
    """Structured, non-secret deterministic lint codes for safe diagnostics."""

    def __init__(self, issues):
        self.issue_codes = tuple(sorted(set(str(issue) for issue in issues)))
        super().__init__('Hasil penulisan melanggar panduan: ' +
                         ', '.join(self.issue_codes))
