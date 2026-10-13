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
    system=("Anda editor berita Unfounded Theory. Edit HANYA field yang diminta berdasarkan evidence JSON, jangan ciptakan fakta, URL, waktu, kutipan atau angka. "
            "Highlight dalam Title Case tidak ALL CAPS dan tidak membocorkan inti; jangan pakai em dash. "
            "Caption empat atau lima paragraf pendek, bahasa Indonesia natural seperti cerita, paragraf pertama langsung menjawab highlight, lalu mekanisme dan dampak faktual yang runut, 5W1H, paragraf terakhir pertanyaan kecuali tragedi. "
            "Kembalikan JSON dengan satu properti 'text'. Tidak boleh menambahkan hashtag ke caption.")
    value=generate_json(system+editorial_instructions(),payload,temperature=0.25,role="rewrite")["text"].strip()
    if not value:raise ValueError("Revisi kosong")
    if "—" in value or "--" in value:raise ValueError("Dilarang em dash")
    return value
