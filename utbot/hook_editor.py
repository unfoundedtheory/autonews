"""Evidence-bounded hook suggestions for an editor to choose in Telegram.

A model's suggestions are not evidence verification. Never auto-approve them.
"""
import re
from .ai_provider import generate_json
from .quality_control import assess
from .renderer import cover_fits
from .config import CONFIG

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

COVER_FIT_SYSTEM = HOOK_SYSTEM + """
Perbaiki highlight agar benar-benar muat dalam tepat empat baris cover 1080x1350.
Pilih kalimat ringkas 50-85 karakter yang tetap akurat berdasarkan evidence.
Tawarkan hingga enam opsi pada array JSON 'options' tanpa membuat fakta baru.
"""

def cover_fit_alternative(draft,story,*,llm=None):
    if not story or len(story.evidence or []) < 2:
        raise ValueError('Tidak ada bukti yang cukup untuk mengubah hook.')
    if llm is None:
        llm=lambda system,data:generate_json(system,data,temperature=0.28,role='draft')
    payload={'headline_source':story.title,'current_hook':draft.highlight,'caption':draft.caption,
             'verified_evidence':[{'claim':e.get('claim'),'quote':e.get('quote')} for e in story.evidence[:6]]}
    response=llm(COVER_FIT_SYSTEM,payload)
    choices=response.get('options') if isinstance(response,dict) else None
    if not isinstance(choices,list):
        raise ValueError('Pilihan hook tidak tersedia.')
    reference=' '.join([story.title,draft.caption,draft.highlight]+[
        str(e.get('claim') or '')+' '+str(e.get('quote') or '') for e in story.evidence])
    numbers=set(re.findall(r'\d+(?:[.,]\d+)?',reference))
    for raw in choices[:8]:
        if not isinstance(raw,str):continue
        candidate=raw.strip().rstrip('.')
        if candidate.casefold()==draft.highlight.strip().casefold():continue
        if not set(re.findall(r'\d+(?:[.,]\d+)?',candidate)).issubset(numbers):continue
        if not cover_fits(candidate,CONFIG.font_path):continue
        if assess(candidate,draft.caption,draft.hashtags,story.evidence,
                  tragedy=bool(draft.is_tragedy),check_cover=False)['passed']:
            return candidate
    raise ValueError('Tidak ada highlight valid yang muat empat baris. Gunakan revisi manual.')
