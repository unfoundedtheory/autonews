"""Validate owner-typed hook WITHOUT rephrasing it with AI.

Scientific claims still require independent editorial QC before publication.
"""
import re
from .editorial import read_editorial_guide
from .renderer import require_cover_fit
from .accent import accent_for_hook


def validate_typed_hook(text, story, font_path=None):
    """Reject unrenderable/unsupported numeric claims but retain exact wording."""
    read_editorial_guide()
    if not isinstance(text,str):
        raise ValueError('Hook harus berupa teks Telegram.')
    value=text.strip()
    if '\n' in value or '\r' in value:
        raise ValueError('Kirim satu kalimat hook dalam satu baris saja.')
    if len(value)<45 or len(value)>210:
        raise ValueError('Hook harus memiliki panjang 45–210 karakter agar layak untuk cover.')
    if '—' in value or '--' in value:
        raise ValueError('Hook tidak boleh memakai em dash atau tanda hubung ganda.')
    if value.endswith('.'):
        raise ValueError('Akhir hook tidak menggunakan tanda titik.')
    if value==value.upper():
        raise ValueError('Hook menggunakan Title Case, bukan seluruhnya huruf kapital.')
    if value.startswith('/'):
        raise ValueError('Kirim kalimat hook, bukan perintah bot.')
    # A numeric claim cannot be introduced solely by an unchecked Telegram message.
    evidence=story.evidence or [] if story else []
    reference=' '.join([story.title]+[str(item.get('claim') or '')+' '+
                     str(item.get('quote') or '') for item in evidence]) if story else ''
    supplied=set(re.findall(r'\d+(?:[.,]\d+)?',value))
    allowed=set(re.findall(r'\d+(?:[.,]\d+)?',reference))
    if supplied-allowed:
        raise ValueError('Angka '+', '.join(sorted(supplied-allowed))+
                         ' belum ada dalam bukti sumber. Periksa dulu sumber primer.')
    try:
        require_cover_fit(value,font_path)
    except ValueError as exc:
        raise ValueError('Hook belum muat empat baris cover. '
                         'Persingkat sendiri lalu kirim lagi tanpa mengubah fakta.') from exc
    return value
