"""Deterministic semantic green accents for scientific cover headlines.

Never select a random long word and never leave a stale one-word accent when
the headline contains an established, meaningful multiword scientific phrase.
This is purely typographic emphasis; it does not create or verify claims.
"""
import re

# Editorially preferred meaningful contiguous phrases, most specific first.
PHRASES = (
    'LINGKARAN CAHAYA AURORAL UTUH',
    'LINGKARAN CAHAYA AURORAL',
    'LINGKARAN CAHAYA',
    'PIRAMIDA RAKSASA',
    'LAUT JEPANG',
    'TANGAN TUHAN',
    'PARTIKEL DARK MATTER',
    'DARK MATTER',
    'LUBANG HITAM',
    'ASAL USUL ALAM SEMESTA',
    'ALAM SEMESTA',
    'GALAKSI PURBA',
    'ZAMAN PURBA',
    'KEHIDUPAN PURBA',
    'JEJAK KEHIDUPAN',
    'ANGIN MATAHARI',
    'SINYAL ANEH',
    'CINCIN AURORA',
    'CAHAYA AURORAL',
    'AURORA UTUH',
    'PLANET MERAH',
    'KUTUB SELATAN',
    'ANCAMAN AI',
    'KECERDASAN BUATAN',
    'SISTEM TATA SURYA',
    'EVOLUSI MANUSIA',
)
# Common connective or clickbait words are not scientific visual highlights.
STOPWORDS = frozenset("""
ADA ADALAH AKAN AGAR ATAU BAGAIMANA BAHKAN BAGI BARU BERHASIL BISA DALAM
DAN DARI DENGAN DI DIBALIK DIKLAIM DITEMUKAN DIUNGKAP HAMPIR HANYA HARI
INI ITU JADI JIKA KARENA KE KEMBALI KETIKA LAGI LEBIH LUAR MASIH MENJADI
MENGAPA MEREKAM MEREKA MUNGKIN NAMUN PADA PARA PERNAH PERTAMA SAAT
SALAH SATU SELAMA SEPERTI SETELAH SEBELUM SEBUAH SEDANG SANGAT TANPA
TENTANG TEPAT TERNYATA TIDAK UTUH UNTUK YANG
""".split())
ANCHORS = frozenset("""
AURORA AURORAL CAHAYA LINGKARAN PIRAMIDA GALAKSI NEBULA NEUTRINO
ICECUBE FOSIL PURBA MARS BUMI BULAN PLANET MATAHARI METEOR KOMET
BINTANG LUBANG HITAM DARK MATTER LAUT JEPANG TANGAN TUHAN
KEHIDUPAN GENETIK EVOLUSI ROBOTIK ILMUWAN SEMESTA KOSMIK AI
""".split())


def _tokens(value):
    return re.findall(r'[\w]+(?:-[\w]+)*', str(value or '').upper())


def accent_for_hook(text, existing=()):
    """Return 1-5 contiguous important words, not a random isolated adjective.

    Exact high-salience expressions take priority even if an earlier generated
    cover stored only the first word. Otherwise respect editor/model choices
    when they are meaningful, with a deterministic topic-first fallback.
    """
    words=_tokens(text)
    if not words:
        return []
    # Match whole consecutive tokens: phrases are never guessed or inserted.
    for phrase in PHRASES:
        phrase_words=phrase.split()
        for start in range(len(words)-len(phrase_words)+1):
            if words[start:start+len(phrase_words)]==phrase_words:
                return phrase_words

    selected=set()
    for proposed in existing or ():
        selected.update(w for w in _tokens(proposed) if w in words and w not in STOPWORDS)
    preserved=[w for w in words if w in selected]
    # Two independently selected scientific terms can be intentional.
    if len(preserved)>=2:
        return list(dict.fromkeys(preserved))[:5]

    # Prefer a named subject to incidental verbs/adjectives.
    index=next((i for i,w in enumerate(words) if w in ANCHORS),None)
    if index is None and preserved:
        index=words.index(preserved[0])
    if index is None:
        meaningful=[(i,w) for i,w in enumerate(words) if w not in STOPWORDS and len(w)>=5]
        if not meaningful:
            return []
        index=max(meaningful,key=lambda pair:(len(pair[1]),-pair[0]))[0]

    # Highlight one noun phrase where possible, not unrelated parts of headline.
    start=index
    if index>0 and words[index-1] not in STOPWORDS and len(words[index-1])>3:
        start=index-1
    end=index+1
    while end<len(words) and end-start<3 and words[end] not in STOPWORDS:
        end+=1
    return words[start:end][:5]
