"""Conservative photo search gate. A matching filename is NOT proof of identity.

This filters clearly mismatched search results before rendering. All results
still require editor review of both topic relevance and usage rights.
"""
import re


STOP = {
    'nasa','esa','new','latest','study','research','researchers','scientists','scientific',
    'telescope','astronomy','science','space','planet','photo','image','picture','shot',
    'view','graphic','picture','artist','illustration','artistimpression',
    'a','and','an','at','from','by','in','the','of','for','with','on','this'
}


def _terms(value):
    return {w for w in re.findall(r'[a-z0-9]+', (value or '').casefold())
            if (len(w) >= 4 or any(c.isdigit() for c in w)) and w not in STOP}


def likely_same_subject(search_query, item):
    """True means possible topic match, NEVER automatic licence/identity approval."""
    haystack = ' '.join(str(item.get(k) or '') for k in ('title', 'description', 'credit'))
    wanted = _terms(search_query)
    if not wanted:
        return False
    present = _terms(haystack)
    if len(wanted & present) >= 2:
        return True
    # Fused scientific catalog identifier e.g. MSH 15-52 -> MSH1552.
    needle = re.sub(r'[^a-z0-9]', '', search_query.casefold())
    fused = re.sub(r'[^a-z0-9]', '', haystack.casefold())
    return bool(len(needle) >= 7 and needle in fused)

def search_queries(query, *, story_title=''):
    """Shorten over-specific search phrases without losing mission identity.

    Commons full-text search performs poorly with dozens of ANDed keywords.
    Search an identifiable subject first, then broaden cautiously; each result
    must separately pass the subject-matching gate.
    """
    words=re.findall(r'[A-Za-z0-9-]+', (query or '').strip())
    anchor=[w for w in words if len(w)>=4 and w.casefold() not in
            {'mission','space','nasa','spacecraft','satellite','solar','wind',
             'magnetosphere','ionosphere','link','explorer','science','earth','esa','cas'}]
    choices=[]
    def add(value):
        value=' '.join(value.split()).strip()
        if value and value.casefold() not in {x.casefold() for x in choices}:
            choices.append(value[:100])
    if words:
        # Prioritise the full proper mission name when available, not 8+ generic terms.
        first=words[0]
        if len(first)>=4 and first.casefold() not in {'solar','space','earth','science'}:
            add(first+' spacecraft')
            add(first+' mission')
        add(' '.join(words[:3]))
    if anchor:
        add(anchor[0]+' spacecraft')
    for w in re.findall(r'\b[A-Z][A-Z0-9]{2,}\b',story_title or '')[:2]:
        add(w+' spacecraft')
    add(query or story_title)
    return choices[:4]
