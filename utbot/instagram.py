"""Official Instagram Graph API adapter. Never automatically repeat uncertain media_publish calls."""
import re
from urllib.parse import urlparse
import httpx

class InstagramPublisher:
    def __init__(self, base, version, ig_user_id, token, transport=None):
        self.base=base.rstrip("/"); self.version=version; self.ig_id=ig_user_id; self.token=token
        self.transport=transport
    def _request(self,method,path,**kwargs):
        with httpx.Client(timeout=30,transport=self.transport) as client:
            r=client.request(method,f"{self.base}/{self.version}/{path}",headers={"Authorization":f"Bearer {self.token}"},**kwargs)
            r.raise_for_status()
            return r.json()
    def create_container(self,image_url,caption):
        if not image_url.startswith("https://"): raise ValueError("Public HTTPS image URL required")
        d=self._request("POST",f"{self.ig_id}/media",data={"image_url":image_url,"caption":caption})
        return d["id"]
    def create_carousel_child(self,image_url):
        if not image_url.startswith("https://"):
            raise ValueError("Public HTTPS image URL required")
        return self._request("POST", f"{self.ig_id}/media",
                             data={"image_url":image_url, "is_carousel_item":"true"})["id"]

    def create_carousel_container(self,children,caption):
        if not 2 <= len(children) <= 10 or not all(children):
            raise ValueError("Carousel API memerlukan 2–10 child containers")
        return self._request("POST", f"{self.ig_id}/media",
                             data={"media_type":"CAROUSEL",
                                   "children":",".join(children),"caption":caption})["id"]

    def container_status(self,container_id):
        return self._request("GET",container_id,params={"fields":"status_code,status"}).get("status_code")
    def publish(self,container_id):
        return self._request("POST",f"{self.ig_id}/media_publish",data={"creation_id":container_id})["id"]


_SOCIAL_DOMAINS={
    'threads.net':'threads','threads.com':'threads','instagram.com':'instagram',
    'tiktok.com':'tiktok','twitter.com':'twitter','x.com':'x',
    'facebook.com':'facebook','pinterest.com':'pinterest'
}

def _social_source(url):
    """Return network and explicit handle only; never infer who owns a photo."""
    parsed=urlparse((url or '').strip())
    host=(parsed.hostname or '').lower().removeprefix('www.').removeprefix('m.')
    network=_SOCIAL_DOMAINS.get(host)
    if not network:return None,None
    parts=[s for s in parsed.path.split('/') if s]
    if not parts:return network,None
    candidate=parts[0].lstrip('@')
    if not re.fullmatch(r'[A-Za-z0-9._-]{2,60}',candidate):
        return network,None
    if candidate in ('p','reel','reels','post','posts','explore','stories','share'):
        return network,None
    return network,candidate


def photo_credit_line(draft, *, allow_missing=False):
    """Short, human-supplied author credit. Source URL is NOT proof of ownership."""
    credit=re.sub(r'\s+', ' ', (getattr(draft,'image_credit',None) or '')).strip()
    credit=re.sub(r'^(?:Photo\s+by|Foto|Kredit\s+foto|Credit)\s*:\s*',
                  '',credit,flags=re.IGNORECASE).strip()
    if not credit or credit.casefold() in {
            'unknown','unknown author','n/a','tidak diketahui','belum diisi',
            'kredit foto: perlu diisi oleh editor'}:
        if allow_missing:
            # Preview may omit an unknown credit, but must never expose a
            # source URL as a substitute for the actual photographer.
            return ''
        raise ValueError('Kredit foto asli wajib diisi sebelum publikasi Instagram.')

    net,handle=_social_source(credit if credit.startswith('https://')
                              else getattr(draft,'media_page_url',None))
    direct_net,direct_handle=_social_source(credit) if credit.startswith('https://') else (None,None)
    if direct_net and direct_handle:
        credit=f'{direct_net}/{direct_handle}'
    else:
        social=re.fullmatch(r'(?i)(threads|instagram|tiktok|twitter|x|facebook|pinterest)/@?([A-Za-z0-9._-]{2,60})',credit)
        if social:
            credit=f'{social.group(1).lower()}/{social.group(2)}'
        elif net and handle and credit.lstrip('@').casefold()==handle.casefold():
            credit=f'{net}/{handle}'
        elif net and re.fullmatch(r'@[A-Za-z0-9._-]{2,60}',credit):
            credit=f'{net}/{credit[1:]}'
    if len(credit)>140:
        # Do not silently trim licensed photographer names; ask for a concise
        # but accurately attributable credit in Telegram before approval.
        raise ValueError('Kredit foto terlalu panjang. Ringkas nama kreator secara akurat.')
    return 'Photo by : '+credit


def caption_text(draft, *, allow_missing_credit=False):
    """Same caption layout for Telegram preview and Instagram publication."""
    body=(draft.caption or '').strip()
    # A separate metadata-derived credit is authoritative so photo swaps cannot
    # accidentally retain the previous photographer in an editable caption.
    body='\n'.join(line for line in body.split('\n')
                   if not re.match(r'^\s*(?:Photo\s+by|Foto|Kredit\s+foto|Sumber\s+gambar)\s*:',line,re.I)).strip()
    parts=[value for value in (
        body,photo_credit_line(draft,allow_missing=allow_missing_credit),
        ' '.join(draft.hashtags)) if value]
    content='\n\n'.join(parts)
    if len(content)>2200:
        raise ValueError('Caption Instagram melebihi 2.200 karakter termasuk kredit foto')
    return content
