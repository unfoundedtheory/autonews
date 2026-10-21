"""First-stage discovery; never equate an RSS headline with fact verification."""
import hashlib
import html
import re
import json
import feedparser
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode,urljoin
from defusedxml import ElementTree
import httpx
from bs4 import BeautifulSoup
from .models import Story
from .editorial import trusted_source

# Official feeds; verify changes to published feed URLs before going live.
SOURCES=[
  # BRIN: official Indonesian primary research releases. Only article links
  # with explicit space/astronomy subjects pass the bounded listing parser.
  {"name":"BRIN Indonesia Space","url":"https://brin.go.id/news",
   "format":"brin_listing","topic":"space"},
  {"name":"BRIN Riset Penerbangan dan Antariksa",
   "url":"https://brin.go.id/orpa/posts/kabar",
   "format":"brin_listing","topic":"space"},
  # The official APOD API replaced the legacy feed; RSS stays as fallback.
  {"name":"NASA Astronomy Picture of the Day",
   "url":"https://science.nasa.gov/wp-json/wp/v2/apod-basic?per_page=10",
   "fallback_urls":["https://science.nasa.gov/feed/apod-basic/"],
   "format":"apod_json","topic":"astronomy"},
  {"name":"NASA Science","url":"https://science.nasa.gov/feed/",
   "fallback_urls":["https://www.nasa.gov/feed/"],"topic":"space"},
  {"name":"NASA News","url":"https://www.nasa.gov/news-release/feed/","topic":"space"},
  {"name":"ESA Space Science","url":"https://www.esa.int/rssfeed/Our_Activities/Space_Science","topic":"astronomy"},
  # ESO's former /news/feed/ returns HTTP 400. Parse only dated official release links.
  {"name":"ESO News","url":"https://www.eso.org/public/news/","format":"eso_listing","topic":"astronomy"},
  {"name":"EMBL News","url":"https://www.embl.org/news/feed/","topic":"biology"},
  {"name":"Google DeepMind","url":"https://deepmind.google/blog/rss.xml","topic":"ai"},
]


# A relevant Indonesia/space story outranks global stories, but neither an
# unrelated local press release nor the word "Indonesia" alone qualifies.
BRIN_SPACE_RE=re.compile(
    r'\b(?:antariksa|astronom\w*|astrofisika|meteor\w*|komet\w*|'
    r'asteroid\w*|satelit\w*|orbit\w*|teleskop\w*|'
    r'observatorium|ionosfer|gerhana|space weather|benda langit|'
    r'cuaca antariksa|roket\w*|planet\w*|'
    r'galaksi\w*|bintang\w*|hilal|langit malam)\b', re.IGNORECASE)
INDONESIA_GEO_RE=re.compile(
    r'\b(?:indonesia|nusantara|jakarta|jawa|sumatra|sumatera|'
    r'kalimantan|sulawesi|papua|bali|nusa tenggara|maluku|'
    r'bandung|bogor|biak|timau|kupang|yogyakarta|'
    r'lapan|brin|bmkg)\b', re.IGNORECASE)


def is_indonesia_space_story(story):
    """Rank a space headline with explicit local context or BRIN provenance.

    Editorial fact-checking still has to establish when, where and what
    actually occurred. This signal is NEVER itself evidence of a claim.
    """
    title=str(story.title or '')
    if not BRIN_SPACE_RE.search(title):
        return False
    name=str(story.source_name or '')
    return bool(INDONESIA_GEO_RE.search(title) or
                'brin' in name.casefold())


def candidate_priority(story):
    """Lower score is first: Indonesian space, worldwide space, then others."""
    if is_indonesia_space_story(story):
        return 0
    if story.topic in ('astronomy','space'):
        return 1
    return 2


def sort_candidates(stories):
    """Stable newest-first ranking inside each science priority without AI costs."""
    def unix(value):
        if value is None:return float('-inf')
        if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    return sorted(stories,key=lambda st:(
        candidate_priority(st),
        -unix(st.published_at),
        -unix(st.created_at),
        st.id or ''))


def evergreen_sources(now=None):
    """Bounded archive pass when current feeds are exhausted.

    The APOD WordPress archive is paged; rotate among older pages by date.
    Editorial review checks facts and distinguishes historical events from news.
    """
    now=now or datetime.now(timezone.utc)
    page=2+(now.toordinal()%40)
    return [
        {"name":"NASA APOD Archive",
         "url":f"https://science.nasa.gov/wp-json/wp/v2/apod-basic?per_page=25&page={page}",
         "format":"apod_json","topic":"astronomy"},
        {"name":"NASA History",
         "url":"https://www.nasa.gov/history-news-and-articles/",
         "format":"history_listing","topic":"science"},
        {"name":"Nature Archaeology",
         "url":"https://www.nature.com/subjects/archaeology",
         "format":"archaeology_listing","topic":"archaeology"},
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
    # Allow a simple, harmless DOCTYPE while rejecting entity expansion,
    # internal subsets and remote DTDs. Never resolve XML external entities.
    if re.search(br'<!\s*ENTITY\b',payload,re.IGNORECASE):
        raise ValueError('Feed dengan deklarasi entity tidak diizinkan.')
    if re.search(br'<!\s*DOCTYPE\b',payload,re.IGNORECASE):
        safe = re.compile(br'<!DOCTYPE\s+[A-Za-z_][A-Za-z0-9_.:-]*\s*>',re.IGNORECASE)
        declarations = re.findall(br'<!\s*DOCTYPE[^>]*>',payload,re.IGNORECASE|re.DOTALL)
        if len(declarations)!=1 or not safe.fullmatch(declarations[0]):
            raise ValueError('Feed dengan DTD/entity eksternal tidak diizinkan.')
        payload=payload.replace(declarations[0],b'',1)
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
    if not out and any(node.tag.rsplit('}',1)[-1].lower() in {'item','entry'} for node in root.iter() if isinstance(node.tag,str)):
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

def parse_apod_json(content):
    """Ingest NASA's official APOD WordPress API, never generic arbitrary JSON."""
    try:
        decoded=json.loads(content)
    except (ValueError,TypeError) as exc:
        raise ValueError('NASA APOD API tidak mengembalikan JSON valid.') from exc
    items=decoded if isinstance(decoded,list) else [decoded] if isinstance(decoded,dict) else []
    result=[]
    for item in items:
        if not isinstance(item,dict):continue
        title=item.get('title') or ''
        if isinstance(title,dict):title=title.get('rendered') or title.get('raw') or ''
        title=html.unescape(re.sub(r'<[^>]+>','',str(title))).strip()
        url=str(item.get('link') or item.get('url') or '').strip()
        if not title or not trusted_source(url):continue
        raw=item.get('date_gmt') or item.get('date') or item.get('published_at')
        try:
            if raw:
                pub=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
                pub=pub.replace(tzinfo=timezone.utc) if pub.tzinfo is None else pub.astimezone(timezone.utc)
            else: pub=None
        except ValueError:pub=None
        result.append({'title':title,'url':canonicalize(url),'pub':pub,'summary':''})
    if not result:
        raise ValueError('NASA APOD API tidak memiliki artikel valid.')
    return result


def parse_eso_listing(content):
    """Read only *dated* ESO press releases from ESO's public official listing."""
    if isinstance(content,bytes):
        if len(content)>2_000_000:raise ValueError('Halaman ESO terlalu besar.')
        content=content.decode('utf-8','replace')
    soup=BeautifulSoup(content,'html.parser')
    out=[];seen=set()
    pattern=re.compile(r'^/public/news/eso\d{4}[a-z]?/?$',re.IGNORECASE)
    date_re=re.compile(r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})\b',re.IGNORECASE)
    for a in soup.find_all('a',href=True):
        url=urljoin('https://www.eso.org',a['href'])
        if not trusted_source(url) or not pattern.match(urlsplit(url).path) or url in seen:
            continue
        # Date must be attached to its own release item, not page-wide text.
        context=a.parent
        stamp=None
        for _ in range(4):
            if context is None or context.name in ('body','html','main'):break
            # A date may belong to a neighboring release: require that the
            # smallest inspected container has just this one press-release link.
            press_links=[el for el in context.find_all('a',href=True)
                         if pattern.match(urlsplit(urljoin('https://www.eso.org',el['href'])).path)]
            if len(press_links)>1:break
            piece=context.get_text(' ',strip=True)[:1200]
            found=date_re.search(piece)
            if found:
                try:stamp=datetime.strptime(found.group(1).title(),'%d %B %Y').replace(tzinfo=timezone.utc)
                except ValueError:pass
                break
            if context.name in ('article','li'):break
            context=context.parent
        title=a.get_text(' ',strip=True)
        if title and stamp:
            seen.add(url)
            out.append({'title':html.unescape(title),'url':canonicalize(url),'pub':stamp,'summary':''})
    return out



def parse_evergreen_listing(content, *, site):
    """Extract article HEADLINES from a vetted official topic listing, not site navigation."""
    if isinstance(content,bytes):
        if len(content)>2_000_000:raise ValueError('Daftar arsip terlalu besar.')
        content=content.decode('utf-8','replace')
    soup=BeautifulSoup(content,'html.parser')
    for el in soup(['script','style','nav','footer','header','form']):el.decompose()
    main=soup.find('main') or soup
    results=[];found=set()
    for heading in main.find_all(['h2','h3','h4']):
        anchor=heading.find('a',href=True) or heading.find_parent('a',href=True)
        if not anchor:continue
        link=urljoin(site,anchor.get('href',''))
        if not trusted_source(link):continue
        host=urlsplit(link).hostname or ''
        path=urlsplit(link).path
        if site.startswith('https://www.nature.com/'):
            if host not in ('www.nature.com','nature.com') or not re.match(r'^/(?:articles|news)/[^/]+',path):
                continue
        else:
            if not host.endswith('nasa.gov') or path.rstrip('/') in (
                    '/history','/history-news-and-articles','/'):
                continue
            if not re.search(r'/[a-zA-Z0-9][a-zA-Z0-9-]{10,}/?$',path):
                continue
        title=html.unescape(heading.get_text(' ',strip=True))
        if not 20<=len(title)<=220:continue
        link=canonicalize(link)
        if link in found:continue
        found.add(link)
        # Historical pages may not have a machine-readable publish date.
        # Never fabricate one or claim a finding happened today.
        results.append({'title':title,'url':link,'pub':None,'summary':''})
    if not results:
        raise ValueError('Tidak menemukan artikel arsip yang memenuhi struktur sumber.')
    return results[:45]

def parse_brin_listing(content):
    """Collect only linked space/astronomy releases from BRIN's official news list.

    When the listing is JavaScript-only, fail visibly rather than invent links.
    An unprovided publication date is deliberately left unknown.
    """
    if isinstance(content,bytes):
        if len(content)>2_000_000:
            raise ValueError('Daftar berita BRIN terlalu besar.')
        content=content.decode('utf-8','replace')
    soup=BeautifulSoup(content,'html.parser')
    for tag in soup(['script','style','nav','footer','header','form']):tag.decompose()
    results=[];seen=set()
    article_path_re=re.compile(r'/news/[0-9]+/[a-z0-9-]+/?|/orpa/posts/kabar/[a-z0-9-]+/?', re.IGNORECASE)
    for a in soup.find_all('a',href=True):
        article=urljoin('https://brin.go.id/news',a['href'])
        parts=urlsplit(article)
        if (parts.hostname not in ('brin.go.id','www.brin.go.id')
                or not article_path_re.fullmatch(parts.path) or not trusted_source(article)):
            continue
        title=a.get_text(' ',strip=True)
        if len(title)<24 or title.casefold() in ('selengkapnya','baca selengkapnya'):
            parent=a.find_parent(['article','li']) or a.parent
            heading=parent.find(['h2','h3','h4','h5']) if parent else None
            title=heading.get_text(' ',strip=True) if heading else ''
        title=html.unescape(re.sub(r'\s+',' ',title)).strip()
        if not 24<=len(title)<=220 or not BRIN_SPACE_RE.search(title):
            continue
        url=canonicalize(article)
        if url in seen:continue
        seen.add(url)
        results.append({'title':title,'url':url,'pub':None,'summary':''})
        if len(results)>=40:break
    if not results:
        raise ValueError('Listing BRIN tidak memuat tautan artikel antariksa yang dapat diverifikasi.')
    return results


def parse_source_response(source,url,content):
    if source.get('format')=='brin_listing':
        return parse_brin_listing(content)
    if source.get('format')=='apod_json' and '/wp-json/' in url:
        return parse_apod_json(content)
    if source.get('format')=='eso_listing' and url==source['url']:
        return parse_eso_listing(content)
    if source.get('format') in ('history_listing','archaeology_listing'):
        return parse_evergreen_listing(content,site=url)
    return parse_items(content)

def discover(db, sources=None, fetcher=None, now=None):
    """Collect unverified stories. Broken sources may use vetted official fallbacks."""
    now=now or datetime.now(timezone.utc)
    feeds=sources if sources is not None else SOURCES
    with httpx.Client(timeout=15,follow_redirects=False,
                      headers={'User-Agent':'UnfoundedTheoryNewsroom/0.7 (science news discovery)'}) as client:
        for source in feeds:
            inserted=0;duplicates=0;seen=0;excluded=0
            errors=[];used_url=None
            entries=None
            for url in [source['url']]+list(source.get('fallback_urls') or []):
                try:
                    if not trusted_source(url):
                        raise ValueError('Sumber feed bukan domain primer tepercaya.')
                    if fetcher:
                        raw=fetcher(url)
                    else:
                        response=client.get(url)
                        response.raise_for_status()
                        raw=response.content
                    entries=parse_source_response(source,url,raw)
                    used_url=url
                    break
                except (httpx.HTTPError,ValueError,TypeError) as exc:
                    errors.append(str(exc)[:180])
            if entries is None:
                yield {'feed':source['name'],'error':'; '.join(errors)[:240],
                       'inserted':0}
                continue
            try:
                seen=len(entries)
                for entry in entries:
                    pub=entry['pub']
                    # Evergreen science: original publication can be many years old.
                    # Future dates remain invalid; a verified article is not a breaking alert.
                    if pub and pub > now+timedelta(days=1):
                        excluded+=1
                        continue
                    if not trusted_source(entry['url']):
                        excluded+=1
                        continue
                    ident=fingerprint(entry['url'])
                    if db.query(Story).filter_by(fingerprint=ident).first():
                        duplicates+=1
                        continue
                    story=Story(fingerprint=ident,title=entry['title'],source_url=entry['url'],
                                source_name=source['name'],published_at=pub,topic=source['topic'],
                                verification_status='needs_fact_check',evidence=[])
                    db.add(story)
                    inserted+=1
                db.flush()
            except Exception as exc:
                db.rollback()
                yield {'feed':source['name'],'error':str(exc)[:200],'inserted':0}
                continue
            yield {'feed':source['name'],'inserted':inserted,'seen':seen,
                   'duplicates':duplicates,'excluded':excluded,
                   'fallback_used':bool(used_url and used_url!=source['url'])}
