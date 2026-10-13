"""Official Instagram Graph API adapter. Never automatically repeat uncertain media_publish calls."""
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
    def container_status(self,container_id):
        return self._request("GET",container_id,params={"fields":"status_code,status"}).get("status_code")
    def publish(self,container_id):
        return self._request("POST",f"{self.ig_id}/media_publish",data={"creation_id":container_id})["id"]


def caption_text(draft):
    """Publish caption and hashtags only; retain image credit in draft metadata."""
    credit=(draft.image_credit or '').strip()
    license_name=(draft.photo_license or '').strip()
    photo_line=('Foto: '+credit+(f' ({license_name})' if license_name else '')) if credit else ''
    parts=[draft.caption.strip()]
    parts.append(' '.join(draft.hashtags))
    content='\n\n'.join(parts)
    if len(content)>2200:
        raise ValueError('Caption Instagram melebihi 2.200 karakter termasuk kredit foto')
    return content
