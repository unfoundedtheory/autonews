"""NASA image-library search. Search result ≠ right to republish."""
import httpx

def nasa_photo_candidates(search_terms,limit=5,transport=None):
    """Return candidate media with metadata; all require usage-rights review.

    NASA hosts some non-NASA-owned media. Agency attribution alone is not a license.
    """
    if not search_terms or len(search_terms)>200:
        raise ValueError("Search query must be 1..200 characters")
    with httpx.Client(timeout=20,transport=transport) as client:
        response=client.get("https://images-api.nasa.gov/search",params={"q":search_terms,"media_type":"image","page_size":min(30,max(limit*3,10))})
        response.raise_for_status()
        items=response.json().get("collection",{}).get("items",[])
    result=[]
    for item in items:
        data=(item.get("data") or [{}])[0]
        links=item.get("links") or []
        image_link=next((l.get("href") for l in links if l.get("render")=="image" and str(l.get("href","")).startswith("https://")),None)
        if not image_link: continue
        result.append({"nasa_id":data.get("nasa_id"),"title":data.get("title"),
                       "description":data.get("description",""),"center":data.get("center"),
                       "photographer":data.get("photographer"),"keywords":data.get("keywords",[]),
                       "thumbnail_url":image_link,"metadata_url":item.get("href"),
                       "license_status":"needs_rights_review"})
        if len(result)>=limit:break
    return result
