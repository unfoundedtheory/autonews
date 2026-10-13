"""First-stage discovery; never equate an RSS headline with fact verification."""
import hashlib
import html
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from defusedxml import ElementTree
import httpx
from .models import Story

# Official feeds; verify changes to published feed URLs before going live.
SOURCES=[
  {"name":"NASA News","url":"https://www.nasa.gov/news-release/feed/","topic":"space"},
  {"name":"ESA Space Science","url":"https://www.esa.int/rssfeed/Our_Activities/Space_Science","topic":"astronomy"},
  {"name":"ESO News","url":"https://www.eso.org/public/news/feed/","topic":"astronomy"},
  {"name":"EMBL News","url":"https://www.embl.org/news/feed/","topic":"biology"},
  {"name":"Google DeepMind","url":"https://deepmind.google/blog/rss.xml","topic":"ai"},
]

def canonicalize(url):
    s=urlsplit(url.strip())
    qs=urlencode([(k,v) for k,v in parse_qsl(s.query) if not k.lower().startswith("utm_") and k not in {"fbclid","gclid"}])
    return urlunsplit((s.scheme,s.netloc.lower(),s.path.rstrip("/")+"/" if s.path else "/",qs,""))

def fingerprint(url):
    return hashlib.sha256(canonicalize(url).encode()).hexdigest()

def parse_items(xml):
    if len(xml if isinstance(xml,bytes) else xml.encode()) > 2_000_000:
        raise ValueError('Feed RSS terlalu besar.')
    root=ElementTree.fromstring(xml)
    out=[]
    for item in root.findall(".//item"):
        def value(tag): return (item.findtext(tag) or "").strip()
        raw=value("pubDate")
        try: pub=parsedate_to_datetime(raw).astimezone(timezone.utc) if raw else None
        except Exception: pub=None
        title=html.unescape(value("title"))
        link=value("link")
        if not title or not link.startswith("https://"):continue
        out.append({"title":title,"url":canonicalize(link),"pub":pub,"summary":html.unescape(value("description"))})
    return out

def discover(db, sources=None, fetcher=None, now=None):
    """Unverified candidate collection; candidate does not become publishable."""
    now=now or datetime.now(timezone.utc)
    found=[]
    feeds=sources if sources is not None else SOURCES
    with httpx.Client(timeout=20,follow_redirects=True) as client:
        for source in feeds:
            try:
                if fetcher:
                    raw=fetcher(source["url"])
                else:
                    response=client.get(source["url"])
                    response.raise_for_status()
                    raw=response.content
                for entry in parse_items(raw):
                    pub=entry["pub"]
                    if pub and pub < now-timedelta(days=7):continue
                    ident=fingerprint(entry["url"])
                    if db.query(Story).filter_by(fingerprint=ident).first(): continue
                    story=Story(fingerprint=ident,title=entry["title"],source_url=entry["url"],source_name=source["name"],published_at=pub,topic=source["topic"],verification_status="needs_fact_check",evidence=[])
                    db.add(story); found.append(story)
                db.flush()
            except Exception as exc:
                # Fail a feed, not the whole ingestion; caller gets failures in report.
                yield {"feed":source["name"],"error":str(exc),"inserted":0}
                continue
            yield {"feed":source["name"],"inserted":len([x for x in found if x.source_name==source["name"]])}
