"""First-stage discovery; never equate an RSS headline with fact verification."""
import hashlib
import html
import re
import feedparser
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from defusedxml import ElementTree
import httpx
from .models import Story
from .editorial import trusted_source

# Official feeds; verify changes to published feed URLs before going live.
SOURCES=[
  {"name":"NASA Astronomy Picture of the Day","url":"https://science.nasa.gov/feed/apod-basic/","topic":"astronomy"},
  {"name":"NASA Science","url":"https://science.nasa.gov/feed/","topic":"space"},
  {"name":"NASA News","url":"https://www.nasa.gov/news-release/feed/","topic":"space"},
  {"name":"ESA Space Science","url":"https://www.esa.int/rssfeed/Our_Activities/Space_Science","topic":"astronomy"},
  {"name":"ESO News","url":"https://www.eso.org/public/news/feed/","topic":"astronomy"},
  {"name":"EMBL News","url":"https://www.embl.org/news/feed/","topic":"biology"},
  {"name":"Google DeepMind","url":"https://deepmind.google/blog/rss.xml","topic":"ai"},
]

def canonicalize(url):
    s=urlsplit(url.strip())
    qs=urlencode([(k,v) for k,v in parse_qsl(s.query) if not k.lower().startswith("utm_") and k not in {"fbclid","gclid"}])
    path=s.path.rstrip("/") or "/"
    if path!="/" and "." not in path.rsplit("/",1)[-1]:path+="/"
    return urlunsplit((s.scheme,s.netloc.lower(),path,qs,""))

def fingerprint(url):
    return hashlib.sha256(canonicalize(url).encode()).hexdigest()

def parse_items(xml):
    """Parse valid XML strictly, but recover usable items from malformed official RSS.

    Never interpret an HTML landing page as a successful, empty news feed.
    Only HTTPS article links are admitted here; discover() additionally enforces
    the trusted-primary-source host allowlist and deduplicates candidates.
    """
    payload=xml if isinstance(xml, bytes) else xml.encode('utf-8')
    if not payload.strip():
        raise ValueError('Respons feed kosong.')
    if len(payload)>2_000_000:
        raise ValueError('Feed RSS terlalu besar.')
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b',payload,re.IGNORECASE):
        raise ValueError('Feed dengan DTD/entity eksternal tidak diizinkan.')
    try:
        root=ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        # NASA and other first-party publishers can intermittently emit broken
        # entities. feedparser recovers individual entries rather than dropping
        # the entire official source; a completely broken feed still fails.
        recovered=feedparser.parse(payload,resolve_relative_uris=False)
        if not recovered.version or not recovered.entries:
            raise ValueError('Respons sumber bukan feed RSS/Atom yang dapat dibaca.') from error
        out=[]
        for entry in recovered.entries:
            title=html.unescape(str(entry.get('title') or '').strip())
            link=str(entry.get('link') or '').strip()
            if not title or not link.startswith('https://'):
                continue
            stamp=entry.get('published_parsed') or entry.get('updated_parsed')
            try:
                pub=datetime(*stamp[:6],tzinfo=timezone.utc) if stamp else None
            except (TypeError,ValueError,OverflowError):
                pub=None
            out.append({'title':title,'url':canonicalize(link),'pub':pub,
                        'summary':html.unescape(str(entry.get('summary') or ''))})
        if not out:
            raise ValueError('Feed rusak: tidak ada artikel HTTPS valid yang dapat dipulihkan.')
        return out

    kind=root.tag.rsplit('}',1)[-1].rsplit(':',1)[-1].lower()
    if kind not in {'rss','rdf','feed'}:
        raise ValueError('Respons sumber bukan RSS/Atom (kemungkinan halaman HTML).')
    out=[]
    for item in root.findall('.//item'):
        def value(tag):return (item.findtext(tag) or '').strip()
        raw=value('pubDate')
        try:pub=parsedate_to_datetime(raw).astimezone(timezone.utc) if raw else None
        except (TypeError,ValueError,OverflowError):pub=None
        title=html.unescape(value('title'))
        link=value('link')
        if not title or not link.startswith('https://'):continue
        out.append({'title':title,'url':canonicalize(link),'pub':pub,
                    'summary':html.unescape(value('description'))})
    ns='{http://www.w3.org/2005/Atom}'
    for entry in root.findall(f'.//{ns}entry'):
        title=html.unescape((entry.findtext(f'{ns}title') or '').strip())
        link=next((a.get('href','') for a in entry.findall(f'{ns}link')
                   if a.get('rel','alternate')=='alternate'),'')
        if not title or not link.startswith('https://'):continue
        raw=(entry.findtext(f'{ns}published') or entry.findtext(f'{ns}updated') or '').strip()
        try:pub=datetime.fromisoformat(raw.replace('Z','+00:00')).astimezone(timezone.utc) if raw else None
        except ValueError:pub=None
        out.append({'title':title,'url':canonicalize(link),'pub':pub,
                    'summary':html.unescape(entry.findtext(f'{ns}summary') or '')})
    # A valid XML feed may use RSS item namespaces we do not parse directly.
    if not out and any(tag.rsplit('}',1)[-1].lower() in {'item','entry'} for tag in root.iter()):
        recovered=feedparser.parse(payload,resolve_relative_uris=False)
        for entry in recovered.entries:
            title=html.unescape(str(entry.get('title') or '').strip())
            link=str(entry.get('link') or '').strip()
            if title and link.startswith('https://'):
                stamp=entry.get('published_parsed') or entry.get('updated_parsed')
                pub=datetime(*stamp[:6],tzinfo=timezone.utc) if stamp else None
                out.append({'title':title,'url':canonicalize(link),'pub':pub,
                            'summary':html.unescape(str(entry.get('summary') or ''))})
    return out

def discover(db, sources=None, fetcher=None, now=None):
    """Unverified candidate collection; candidate does not become publishable."""
    now=now or datetime.now(timezone.utc)
    feeds=sources if sources is not None else SOURCES
    with httpx.Client(timeout=20,follow_redirects=True) as client:
        for source in feeds:
            inserted=0
            duplicates=0
            seen=0
            try:
                if fetcher:
                    raw=fetcher(source["url"])
                else:
                    response=client.get(source["url"])
                    response.raise_for_status()
                    raw=response.content
                entries=parse_items(raw)
                seen=len(entries)
                for entry in entries:
                    pub=entry["pub"]
                    if pub and pub < now-timedelta(days=14):continue
                    if not trusted_source(entry["url"]):continue
                    ident=fingerprint(entry["url"])
                    if db.query(Story).filter_by(fingerprint=ident).first():
                        duplicates+=1
                        continue
                    story=Story(fingerprint=ident,title=entry["title"],source_url=entry["url"],
                                source_name=source["name"],published_at=pub,topic=source["topic"],
                                verification_status="needs_fact_check",evidence=[])
                    db.add(story)
                    inserted+=1
                db.flush()
            except Exception as exc:
                # Fail only the affected feed. Other official sources still run.
                yield {"feed":source["name"],"error":str(exc),"inserted":0}
                continue
            yield {"feed":source["name"],"inserted":inserted,"seen":seen,
                   "duplicates":duplicates}
