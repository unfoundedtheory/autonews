"""Optional AI editing with evidence-bound instructions. Never silently invent facts."""
import json
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
