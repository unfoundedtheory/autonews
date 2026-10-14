"""Native Instagram photo music needs an explicit in-app editorial handoff.

Do not silently publish a mute Graph API JPEG under a "music required" request.
Never fabricate a licensed soundtrack, inject unsupported IG API parameters,
or convert the 4:5 cover into a Reel without the editor's approval.
"""
from urllib.parse import urlparse
from .instagram import caption_text

MOODS={
    "astronomy":"cosmic ambient / instrumental sinematik",
    "space":"cosmic ambient / instrumental sinematik",
    "science":"instrumental dokumenter / minimal elektronik",
    "life":"ambient alam / instrumental lembut",
    "biology":"ambient alam / instrumental lembut",
    "archaeology":"cinematic discovery / instrumental misterius",
    "ai":"minimal elektronik / cinematic tension",
}

def mood_for(topic):
    return MOODS.get(str(topic or '').lower(),MOODS['science'])

def instagram_post_url(url):
    """Validate owner-confirmed public post link; no imported tokens/credentials."""
    p=urlparse((url or '').strip())
    host=(p.hostname or '').lower().removeprefix('www.')
    parts=[segment for segment in p.path.split('/') if segment]
    if (p.scheme!='https' or host!='instagram.com' or p.username or p.password
        or len(parts)<2 or parts[0] not in ('p','reel','tv')
        or not parts[1].replace('_','').replace('-','').isalnum()
        or len(parts[1])>80):
        raise ValueError('Kirim tautan posting Instagram: https://www.instagram.com/p/KODE/')
    return 'https://www.instagram.com/'+parts[0]+'/'+parts[1]+'/'

def manual_music_message(draft,story):
    """Give owner actual media+caption to post manually with native music."""
    if not draft.image_url or not draft.image_url.startswith("https://"):
        raise ValueError('Cover HTTPS final belum siap untuk posting dengan musik.')
    return (
        '🎵 SIAP POSTING FEED + MUSIK\n\n'
        f'Draf: {draft.id[:8]} • v{draft.version}\n'
        'Format: feed foto 4:5 (bukan Reel)\n'
        f'Musik: pilih di Instagram ({mood_for(getattr(story,"topic",None))})\n\n'
        '1. Buka Instagram → + → Post.\n'
        '2. Gunakan cover dari tautan berikut, lalu pilih Add music.\n'
        '3. Tempel caption yang dikirim bot (termasuk kredit dan hashtag).\n'
        '4. Publikasikan lalu kirim tautan posting ke bot untuk konfirmasi.\n\n'
        'Cover: '+draft.image_url+'\n\n'
        'Catatan: audio dipilih manual; API feed foto tidak menambahkan lagu. '
        'Bot TIDAK akan memublikasikan versi tanpa musik.'
    )

def manual_music_caption(draft):
    return caption_text(draft)
