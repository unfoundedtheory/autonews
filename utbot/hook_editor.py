"""Evidence-bounded hook suggestions for an editor to choose in Telegram.

A model's suggestions are not evidence verification. Never auto-approve them.
"""
import re
from .ai_provider import generate_json
from .quality_control import assess

HOOK_SYSTEM = """Anda adalah copy editor Unfounded Theory. Buat TIGA ALTERNATIF HIGHLIGHT Instagram bahasa Indonesia berdasarkan evidence yang disediakan.
Setiap hook wajib memantik rasa ingin tahu dengan fakta spesifik, kontras yang benar-benar ada di sumber, atau pertanyaan ilmiah yang penting.
Bukan judul press release. Hindari pembuka "Misi X", "ESA Mengumumkan", "Para Peneliti" atau "Wahana X Akan".
Jangan mengarang tanggal, angka, risiko terhadap manusia, bencana, klaim pertama di dunia, atau akibat langsung yang tidak ada dalam evidence.
Contoh gaya: "Jari Tanganmu Ternyata Berasal Dari Organ Paling Tak Terduga Pada Ikan Purba" atau "Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter". Jangan menyalin contoh.
Pilih tiga angle yang BERBEDA: (1) kontras/kejutan berbasis bukti, (2) rasa penasaran/pertanyaan, (3) implikasi konkret jika didukung fakta.
Gunakan Title Case, panjang 55-110 karakter bila memungkinkan, maksimal 140, tanpa em dash, tidak membocorkan semua jawaban.
Hasil HANYA JSON: {"options":["hook 1","hook 2","hook 3"]}.
"""

def alternatives(draft, story, *, llm=None):
    if not story or not story.evidence or len(story.evidence)<2:
        raise ValueError('Tidak ada bukti primer memadai untuk usulan hook.')
    payload={'headline_source':story.title,'current_hook':draft.highlight,
             'caption':draft.caption,'verified_evidence':[
                {'claim':e.get('claim'),'quote':e.get('quote')} for e in story.evidence[:6]]}
    if llm is None:
        llm=lambda instruction, facts:generate_json(instruction,facts,temperature=0.45,role='draft')
    response=llm(HOOK_SYSTEM,payload)
    candidates=response.get('options') if isinstance(response,dict) else None
    if not isinstance(candidates,list):raise ValueError('Model tidak memberikan daftar hook.')
    reference=' '.join([story.title,draft.caption,draft.highlight]+[
        str(e.get('claim') or '')+' '+str(e.get('quote') or '') for e in story.evidence])
    allowed_numbers=set(re.findall(r'\d+(?:[.,]\d+)?',reference))
    seen={draft.highlight.strip().casefold()}
    options=[]
    for raw in candidates[:6]:
        if not isinstance(raw,str):continue
        candidate=raw.strip().rstrip('.')
        if candidate.casefold() in seen:continue
        if not set(re.findall(r'\d+(?:[.,]\d+)?',candidate)).issubset(allowed_numbers):
            continue
        result=assess(candidate,draft.caption,draft.hashtags,story.evidence,tragedy=bool(draft.is_tragedy))
        if not result['passed']:continue
        seen.add(candidate.casefold())
        options.append(candidate)
        if len(options)==3:break
    if len(options)<2:
        raise ValueError('Belum ada dua alternatif hook yang lolos QC. Coba ulang atau revisi manual.')
    return options
