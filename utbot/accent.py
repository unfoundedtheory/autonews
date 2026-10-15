"""Semantic green highlights that can be spread across a cover headline.

Emphasize independently important subject, action and phenomenon terms,
not necessarily one contiguous region. Keep wording and factual claims intact.
"""
import re

SUBJECT_PHRASES=(
    'KAMERA ROBOTIK', 'PIRAMIDA RAKSASA', 'TANGAN TUHAN',
    'LUBANG HITAM', 'PLANET MERAH', 'WAHANA ANTARIKSA',
    'STRUKTUR RADIO', 'SIMBOL MUSIK', 'GUGUS GALAKSI',
    'ILMUWAN PURBA', 'KECERDASAN BUATAN',
    'EVOLUSI MANUSIA', 'KEHIDUPAN PURBA', 'ROBOT HUMANOID',
)
REFERENCE_COMPARISONS = (
    'LEBIH TUA DARI PIRAMIDA MESIR',
    'LEBIH TUA DARI PIRAMIDA',
    'LEBIH TUA DARI',
)
REFERENCE_PLACES = ('LAUT JEPANG',)
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


# These small role vocabularies are a deterministic fallback for common news
# frames, not a complete semantic understanding of arbitrary stories.
# Prioritize a coherent subject -> consequence -> cause chain over word count.
NEWS_SUBJECTS=(
    'RUMAH SAKIT', 'BANDARA', 'SEKOLAH', 'KOTA', 'DESA',
)
NEWS_IMPACTS=(
    'LUMPUH', 'TERPUTUS', 'TERHENTI', 'TERISOLASI',
    'RUNTUH', 'TERBAKAR', 'TENGGELAM', 'KRISIS',
)
NEWS_CAUSES=(
    'ASAP PEKAT', 'BANJIR BANDANG', 'HUJAN DERAS',
    'KEBAKARAN HUTAN', 'GEMPA KUAT', 'GELOMBANG PANAS',
)
TIME_ANCHORS=('MALAM INI', 'HARI INI', 'PAGI INI', 'BESOK MALAM')
SPACE_OBJECTS=('JEJAK KOMET', 'HUJAN METEOR', 'JEJAK ASTEROID')
SPACE_METRICS=(
    'RATUSAN METEOR PER JAM', 'RIBUAN METEOR PER JAM',
    'PULUHAN METEOR PER JAM',
)

def _story_skeleton(words):
    """Choose semantic anchors only when the headline contains a full story.

    The color selection must read as a truthful mini-headline by itself.
    For unusual stories that cannot be parsed reliably by these safe
    patterns, preserve the existing semantic fallback/editorial review.
    """
    def find(phrases):
        return _phrase_match(words,phrases,set())

    subject=find(NEWS_SUBJECTS)
    impact=find(NEWS_IMPACTS)
    cause=find(NEWS_CAUSES)
    if subject and impact and cause:
        spans=sorted((subject,impact,cause),key=lambda pair:pair[0])
        occupied=set()
        for start,phrase in spans:
            used=set(range(start,start+len(phrase)))
            if occupied & used:
                break
            occupied.update(used)
        else:
            return [' '.join(phrase) for _,phrase in spans]

    when=find(TIME_ANCHORS)
    cosmic=find(SPACE_OBJECTS)
    scale=find(SPACE_METRICS)
    if when and cosmic and scale:
        spans=sorted((when,cosmic,scale),key=lambda pair:pair[0])
        occupied=set()
        for start,phrase in spans:
            used=set(range(start,start+len(phrase)))
            if occupied & used:
                break
            occupied.update(used)
        else:
            return [' '.join(phrase) for _,phrase in spans]
    return None

def accent_for_hook(text, existing=()):
    """Prefer a factual, readable mini-summary when green words stand alone.

    Known headline patterns use a full subject/impact/cause or
    time/object/scale skeleton. Other topics retain conservative semantic
    keyword fallback plus required human visual review. Never rewrite text.
    """
    words=_tokens(text)
    if not words:return []
    story_skeleton=_story_skeleton(words)
    if story_skeleton:
        return story_skeleton
    groups=[]
    used=set()

    def add(start,selected):
        indices=range(start,start+len(selected))
        if (len(groups)>=4 or sum(len(g[1]) for g in groups)+len(selected)>10
                or any(i in used for i in indices)):
            return False
        groups.append((start,selected))
        used.update(indices)
        return True

    # Multi-part observational headlines need all three editorial anchors:
    # subject, unusual shape and scientific object. Prevent the former single
    # trailing "GALAKSI" accent on radio-cluster collision coverage.
    radio_phrases=('STRUKTUR RADIO','SIMBOL MUSIK','GUGUS GALAKSI')
    if sum(_phrase_match(words,(phrase,),set()) is not None
           for phrase in radio_phrases)>=2:
        for phrase in radio_phrases:
            candidate=_phrase_match(words,(phrase,),used)
            if candidate:
                add(*candidate)
        if len(groups)>=2:
            return [' '.join(span) for _,span in sorted(groups,key=lambda x:x[0])]

    # The approved historical-comparison reference intentionally emphasizes
    # subject, location and key comparison, not its generic action "TERKUBUR".
    # The last phrase may continue onto the fifth line.
    reference_comparison=_phrase_match(words,REFERENCE_COMPARISONS,used)
    if reference_comparison:
        subject=_phrase_match(words,SUBJECT_PHRASES,used)
        if subject:add(*subject)
        location=_phrase_match(words,REFERENCE_PLACES,used)
        if location:add(*location)
        add(*reference_comparison)
        return [' '.join(span) for _,span in sorted(groups,key=lambda x:x[0])]

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
        if len(groups)>=4:break
        # An obsolete arbitrary accent should not displace semantic highlights
        # that already occupy a meaningful share of the title.
        if (len(groups)>=2 and
                sum(len(span) for _,span in groups)/len(words)>=0.22):
            break
        if w in desired and w not in STOPWORDS and i not in used:
            add(i,[w])

    # Where the current accents cover under one quarter of a substantial
    # headline, allow one further SCIENTIFIC phrase. Never add filler words
    # merely to satisfy a percentage target.
    if (groups and len(groups)<4 and len(words)>=12 and
            sum(len(span) for _,span in groups)/len(words)<0.25):
        for phrase in PHENOMENON_PHRASES:
            match=_phrase_match(words,(phrase,),used)
            if match and add(*match):
                break

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
