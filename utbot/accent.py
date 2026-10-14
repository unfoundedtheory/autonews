"""Semantic green highlights that can be spread across a cover headline.

Emphasize independently important subject, action and phenomenon terms,
not necessarily one contiguous region. Keep wording and factual claims intact.
"""
import re

SUBJECT_PHRASES=(
    'KAMERA ROBOTIK', 'PIRAMIDA RAKSASA', 'TANGAN TUHAN',
    'LUBANG HITAM', 'PLANET MERAH', 'WAHANA ANTARIKSA',
    'ILMUWAN PURBA', 'KECERDASAN BUATAN',
    'EVOLUSI MANUSIA', 'KEHIDUPAN PURBA', 'ROBOT HUMANOID',
)
ACTION_WORDS=frozenset("""
MEREKAM MEMOTRET MENEMUKAN DITEMUKAN MENGUNGKAP TERUNGKAP
MENCIPTAKAN MENGHIDUPKAN MENGUBAH MEMBUKTIKAN MENDETEKSI
MENYINGKAP TERKUBUR TERSEMBUNYI MENJELAJAH MELACAK
""".split())
PHENOMENON_PHRASES=(
    'DARK MATTER', 'AURORA BOREALIS', 'CAHAYA AURORAL',
    'SINAR-X', 'NEBULA NGC', 'ANGIN MATAHARI', 'TATA SURYA',
    'ALAM SEMESTA', 'LAUT JEPANG', 'ZAMAN PURBA',
)
PHENOMENON_TERMS=frozenset("""
AURORA AURORAL NEUTRINO GALAKSI NEBULA KOSMOS METEOR
KOMET MATAHARI MARS BUMI BULAN PLANET FOSIL DNA
BINTANG ICECUBE SUPERNOVA KUANTUM ASTEROID ANTARTIKA
KOSMIK SEMESTA LAUT SAMUDRA AI
""".split())
STOPWORDS=frozenset("""
ADA ADALAH AKAN AGAR ATAU BAGAIMANA BAHKAN BAGI BARU
BERHASIL BISA DALAM DAN DARI DENGAN DI DIBALIK
DIBANDING DIKLAIM DITEMUKAN DIUNGKAP HAMPIR HANYA HARI
INI ITU JADI JIKA KARENA KE KEMBALI KETIKA LAGI LEBIH
LUAR MASIH MENJADI MENGAPA MEREKA MUNGKIN NAMUN PADA
PARA PERNAH PERTAMA SAAT SALAH SATU SELAMA SEPERTI
SETELAH SEBELUM SEBUAH SEDANG SANGAT TANPA TENTANG
TEPAT TERNYATA TIDAK UNTUK YANG
""".split())

def _tokens(text):
    return re.findall(r'[\w]+(?:-[\w]+)*',str(text or '').upper())

def _phrase_match(words, candidates, occupied):
    """Best available phrase in headline order, longest match at same position."""
    found=[]
    for phrase in candidates:
        tokens=_tokens(phrase)
        for i in range(len(words)-len(tokens)+1):
            indices=range(i,i+len(tokens))
            if words[i:i+len(tokens)]==tokens and not any(k in occupied for k in indices):
                found.append((i,-len(tokens),tokens))
    if not found:return None
    index,_,match=min(found)
    return index,match

def accent_for_hook(text, existing=()):
    """Choose up to three separated emphasis groups, maximum five highlighted words.

    Prefer *who/what* (subject), *what happened* (action), and *why it
    matters* (science phenomenon). A phrase may be one or two words.
    Existing AI suggestions are fallback, not authority over these cues.
    """
    words=_tokens(text)
    if not words:return []
    groups=[]
    used=set()

    def add(start,selected):
        indices=range(start,start+len(selected))
        if (len(groups)>=3 or sum(len(g[1]) for g in groups)+len(selected)>5
                or any(i in used for i in indices)):
            return False
        groups.append((start,selected))
        used.update(indices)
        return True

    # One subject phrase in the early part, if present.
    subject=_phrase_match(words,SUBJECT_PHRASES,used)
    if subject:
        add(*subject)

    # Most meaningful action, keeping subject and verb independently green.
    action=next(((i,[word]) for i,word in enumerate(words)
                 if word in ACTION_WORDS and i not in used),None)
    if action:add(*action)

    # Scientific object/concept; prefer terms in the latter half, where the
    # main phenomenon is usually introduced, not a generic early topic word.
    options=[]
    for phrase in PHENOMENON_PHRASES:
        seq=_tokens(phrase)
        for i in range(len(words)-len(seq)+1):
            if (words[i:i+len(seq)]==seq
                    and all(j not in used for j in range(i,i+len(seq)))):
                options.append((i,seq))
    for i,word in enumerate(words):
        if word in PHENOMENON_TERMS and i not in used:
            options.append((i,[word]))
    if options:
        # Prefer a late, specific phenomenon; do not highlight entire sentences.
        candidate=max(options,key=lambda p:(p[0],len(p[1])))
        add(*candidate)

    # Preserve a human/editor/model highlight when significant slots remain,
    # but do not allow stale random words to displace the three key cues.
    desired={w for phrase in (existing or ()) for w in _tokens(phrase)}
    for i,w in enumerate(words):
        if len(groups)>=3:break
        if w in desired and w not in STOPWORDS and i not in used:
            add(i,[w])

    # Unknown scientific subject: avoid fabricated importance. Pick one
    # content word near the front; optional second near the end for balance.
    if not groups:
        candidates=[(i,w) for i,w in enumerate(words) if len(w)>=5 and w not in STOPWORDS]
        if candidates:
            add(candidates[0][0],[candidates[0][1]])
            if len(candidates)>2:
                add(candidates[-1][0],[candidates[-1][1]])

    # Preserve left-to-right order so Telegram and stored metadata stay clear.
    return [' '.join(span) for _,span in sorted(groups,key=lambda item:item[0])]
