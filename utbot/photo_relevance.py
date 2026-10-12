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
