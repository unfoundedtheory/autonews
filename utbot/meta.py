"""Meta Graph API integration for Facebook Page photos and safe connection checks.

Instagram API requires its own media container / publish flow; a Facebook
Page photo is a separate post. Never infer a photo was cross-posted.
"""
from urllib.parse import urlparse
import json
import httpx


def _public_https(url):
    parsed=urlparse(url or '')
    return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username


class MetaGraph:
    def __init__(self, token, version="v24.0", base="https://graph.facebook.com", transport=None):
        if not token:
            raise ValueError("Meta access token belum dikonfigurasi")
        if not version.startswith('v') or not version[1:].replace('.','').isdigit():
            raise ValueError("Invalid Graph API version")
        if not base.startswith("https://"):
            raise ValueError("Meta Graph harus menggunakan HTTPS")
        self.token=token
        self.version=version
        self.base=base.rstrip('/')
        self.transport=transport

    def request(self, method, path, *, params=None, data=None):
        # Never include tokens in URL or error text.
        with httpx.Client(timeout=30,transport=self.transport) as client:
            res=client.request(method,f"{self.base}/{self.version}/{path.lstrip('/')}",
                               params=params,data=data,
                               headers={"Authorization":f"Bearer {self.token}"})
            if res.is_error:
                raise ValueError(f"Meta Graph HTTP {res.status_code} (details withheld)")
            payload=res.json()
            if not isinstance(payload,dict) or "error" in payload:
                raise ValueError("Unexpected Meta Graph response")
            return payload

    def page_linkage(self, page_id):
        """Check actual Page and linked IG ID; never return access tokens."""
        if not str(page_id).isdigit():
            raise ValueError("Facebook Page ID tidak valid")
        info=self.request('GET',str(page_id),
                          params={'fields':'id,name,instagram_business_account'})
        linked=(info.get('instagram_business_account') or {}).get('id')
        return {'page_id':str(info.get('id') or page_id),
                'page_name':str(info.get('name') or '')[:120],
                'instagram_business_account_id':str(linked) if linked else None}

    def publish_page_photo(self,page_id,image_url,caption):
        """A single Facebook Page photo; no implicit Instagram publishing."""
        if not str(page_id).isdigit():
            raise ValueError("Facebook Page ID tidak valid")
        if not _public_https(image_url):
            raise ValueError("Facebook requires publicly accessible HTTPS image URL")
        if not caption.strip():
            raise ValueError("Caption kosong")
        result=self.request('POST',f'{page_id}/photos',
                            data={'url':image_url,'caption':caption,'published':'true'})
        media_id=result.get('post_id') or result.get('id')
        if not media_id:
            raise ValueError("Meta did not return Facebook photo/post ID; reconcile manually")
        return {'id':str(media_id),'photo_id':str(result.get('id',''))}

    def publish_page_album(self,page_id,images,caption):
        """Publish a multi-photo Page feed post (separate from Instagram carousel).

        Every photo is first uploaded unpublished, then a single /feed post
        attaches those photo IDs. Caller must pre-record the attempt and never
        retry after an ambiguous network/Graph failure.
        """
        if not str(page_id).isdigit() or not 2 <= len(images) <= 20:
            raise ValueError("Facebook album requires 2-20 photos")
        if not caption.strip() or any(not _public_https(url) for url in images):
            raise ValueError("Facebook album requires HTTPS images and a caption")
        attached={}
        for index,url in enumerate(images):
            asset=self.request("POST",f"{page_id}/photos",
                               data={"url":url,"published":"false"})
            media_id=asset.get("id")
            if not media_id:raise ValueError("Facebook image upload ID missing")
            attached[f"attached_media[{index}]"]=json.dumps(
                {"media_fbid":str(media_id)})
        response=self.request("POST",f"{page_id}/feed",
                              data={"message":caption,**attached})
        post_id=response.get("id")
        if not post_id:raise ValueError("Facebook feed post ID missing")
        return {"id":str(post_id),"photo_id":""}
