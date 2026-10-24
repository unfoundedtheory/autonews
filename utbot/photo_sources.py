"""Multi-source image discovery for news covers.

Visual/topic relevance is the selection criterion. License information, when
known, is metadata for attribution and is never used to discard a candidate.
Every chosen photo must still pass the source-subject match and actual JPEG
intake before the final editorial render can be marked ready.
"""
from urllib.parse import urlparse
import httpx
from .media import find_article_photo, find_photos
from .photos import nasa_photo_candidates
from .photo_relevance import photo_subject_match, search_queries

OPENVERSE_API = "https://api.openverse.org/v1/images/"
AGENT = "UnfoundedTheoryEditorialBot/1.0 (https://github.com/unfoundedtheory/autonews; unfoundedtheory@gmail.com)"


def openverse_photo_candidates(query, limit=8, transport=None):
    """Anonymous Openverse image search (not HTML scraping)."""
    with httpx.Client(timeout=10, transport=transport,
                      headers={"User-Agent": AGENT, "Accept": "application/json"}) as client:
        response = client.get(OPENVERSE_API, params={"q": query[:100], "page_size": min(limit * 2, 20)})
        response.raise_for_status()
        items = response.json().get("results", [])
    result = []
    for item in items:
        if item.get("mature") is True:
            continue
        url = str(item.get("url") or "")
        if urlparse(url).scheme != "https":
            continue
        title = str(item.get("title") or "")[:250]
        tags = " ".join(str(tag.get("name") or "") for tag in (item.get("tags") or [])
                        if isinstance(tag, dict))
        result.append({
            "source": "openverse",
            "image_url": url, "original_url": url,
            "page_url": str(item.get("foreign_landing_url") or item.get("detail_url") or "")[:800],
            "title": title, "description": (title + " " + tags)[:900],
            "credit": item.get("creator") or item.get("attribution") or None,
            "license": item.get("license") or None,
            "license_url": item.get("license_url") or None,
        })
        if len(result) >= limit:
            break
    return result


def nasa_cover_candidates(query, limit=8):
    """Normalize NASA Image and Video Library search results for cover intake."""
    items = nasa_photo_candidates(query, limit=limit)
    out = []
    for item in items:
        url = item.get("thumbnail_url")
        if not url or not url.startswith("https://"):
            continue
        nasa_id = item.get("nasa_id")
        out.append({
            "source": "nasa_library",
            "image_url": url, "original_url": url,
            "page_url": "https://images.nasa.gov/details-" + str(nasa_id)
                        if nasa_id else "https://images.nasa.gov/",
            "title": str(item.get("title") or "")[:250],
            "description": str(item.get("description") or "")[:1000],
            "credit": item.get("photographer") or item.get("center") or "NASA Image Library",
            "license": None, "license_url": None,
        })
    return out


def discover_cover_candidates(story, query=None, *, commons_search=None, source_finder=None,
                              nasa_search=None, openverse_search=None, max_variants=4):
    """Source article first; then NASA library, Wikimedia and Openverse.

    Relevance is checked against the original article subject, not simply
    an AI-generated query. Each provider failing is isolated from the others.
    """
    commons_search = commons_search or find_photos
    source_finder = source_finder or find_article_photo
    nasa_search = nasa_search or nasa_cover_candidates
    openverse_search = openverse_search or openverse_photo_candidates
    found, errors, seen = [], [], set()
    def append(candidate, term, *, source):
        if not isinstance(candidate, dict):
            return
        url = str(candidate.get("image_url") or "")
        if not url.startswith("https://") or url in seen:
            return
        if not photo_subject_match(term, candidate, story.title):
            return
        seen.add(url)
        result = dict(candidate)
        result.setdefault("source", source)
        found.append(result)

    try:
        hero = source_finder(story.source_url, subject=story.title)
        if hero:
            append(hero, story.title, source="official_article")
    except (ValueError, OSError, httpx.HTTPError) as exc:
        errors.append("article:" + type(exc).__name__)
    if found:
        return found, errors

    variants = search_queries(query or story.title, story_title=story.title)[:max_variants]
    # Search each provider before concluding that the article has no usable
    # subject-specific image. No license allowlist; no generic filler.
    for term in variants:
        for name, search in (("nasa", nasa_search), ("commons", commons_search),
                             ("openverse", openverse_search)):
            try:
                items = search(term, limit=8)
                for candidate in items:
                    append(candidate, term, source=name)
            except (ValueError, OSError, httpx.HTTPError) as exc:
                reason = ("http_" + str(exc.response.status_code)
                          if isinstance(exc, httpx.HTTPStatusError)
                          else type(exc).__name__)
                errors.append(name + ":" + reason)
        if len(found) >= 3:
            break
    return found[:12], errors
