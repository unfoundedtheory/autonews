"""Optional AI editing with evidence-bound instructions. Never silently invent facts."""
import json
import re
from .editorial import lint
from .ai_provider import generate_json
from .editorial import editorial_instructions

def rewrite(field,instruction,draft,story):
    if field not in ("highlight","caption"):
        raise ValueError("Only text fields can be revised by AI")
    if not story.evidence:
        raise RuntimeError("Tidak ada evidence sheet untuk menjaga akurasi.")
    payload={"story":story.title,"evidence":story.evidence,"existing_highlight":draft.highlight,"existing_caption":draft.caption,"hashtags":draft.hashtags,"edit_field":field,"instruction":instruction}
    system=("Anda editor revisi Unfounded Theory. Edit HANYA field diminta berdasar "
            "evidence primer yang disertakan. Ikuti seluruh Markdown panduan resmi. "
            "Untuk highlight gunakan curiosity gap faktual, Title Case, tidak membocorkan "
            "jawaban, tanpa pengulangan kata penting atau framing risiko palsu. "
            "Untuk caption gunakan 4-5 paragraf, pembuka adegan/angka/pertanyaan, "
            "alur bercerita yang mengalir dengan micro-hook dan pivot kontras, "
            "tetap mencakup 5W1H, angka/sumber saat tersedia, batas bukti dan "
            "penutup open-loop question kecuali tragedi yang empatik. "
            "Tidak boleh menambah fakta, URL, waktu, kutipan atau angka, "
            "tidak memakai em dash atau '--', tidak memakai filsafat, filler atau "
            "gaya press release. Output JSON dengan satu properti 'text'. "
            "Jangan masukkan hashtag ke caption.")
    value=generate_json(system+editorial_instructions(),payload,temperature=0.25,role="rewrite")["text"].strip()
    if not value:raise ValueError("Revisi kosong")
    if "—" in value or "--" in value:raise ValueError("Dilarang em dash")
    return value


def normalize_caption_format(value):
    """Normalize presentation only; never invent facts or questions."""
    if not isinstance(value,str):
        raise ValueError('Caption AI harus berupa teks.')
    value=value.replace('\\r\\n','\\n').replace('\\r','\\n').strip()
    # Model often places the five hashtags at the bottom despite instructions.
    # Hashtags are stored separately in Draft.hashtags.
    value=re.sub(r'(?<!\\w)#[A-Za-z0-9_]+', '', value)
    # A single newline between prose blocks is a paragraph separator.
    parts=[re.sub(r'\\s+', ' ', p).strip() for p in re.split(r'\\n+',value) if p.strip()]
    # Do not invent additional paragraphs; let AI repair missing structure.
    # Excess line-separated fragments may be grouped without altering words.
    if len(parts)>5:
        parts=parts[:4]+[' '.join(parts[4:])]
    return '\\n\\n'.join(parts).strip()
