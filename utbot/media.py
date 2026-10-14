"""Wikimedia Commons candidate discovery, license metadata, safe image intake, and storage.

Commons file descriptions can contain inaccurate/ambiguous licensing. Candidates therefore
require a human rights review even when their machine-readable license appears suitable.
"""
import html
import re
from pathlib import Path
from urllib.parse import urlparse,urljoin
from PIL import Image, UnidentifiedImageError
import httpx
from bs4 import BeautifulSoup
from .editorial import trusted_source
from .config import CONFIG
from .photo_relevance import likely_same_subject

COMMONS_API='https://commons.wikimedia.org/w/api.php'
# Editorial redistribution is permitted by these licenses when attribution/other terms are satisfied.
LICENSE_ALLOW={'CC0','CC BY 4.0','CC BY 3.0','CC BY 2.0','CC BY-SA 4.0','CC BY-SA 3.0','CC BY-SA 3.0 IGO','CC BY-SA 2.0','Public domain','PD-old','PD-USGov','PDM 1.0'}

def find_article_photo(article_url,transport=None,*,subject=None):
    """Candidate hero image *from the exact official source article*.

    This is only a preview candidate, not proof of reuse rights. Credits and
    licensing must be supplied by the human editor before final approval.
    """
    if not trusted_source(article_url):
        raise ValueError('Foto artikel hanya boleh dicari dari sumber primer resmi.')
    with httpx.Client(timeout=16,follow_redirects=False,transport=transport,
                      headers={'User-Agent':'UnfoundedTheoryEditorialBot/0.7 (official-source preview)'}) as client:
        response=client.get(article_url)
        response.raise_for_status()
        typ=response.headers.get('content-type','').split(';')[0].strip().lower()
        if typ not in ('text/html','application/xhtml+xml'):
            raise ValueError('Artikel resmi tidak menyediakan HTML untuk foto.')
        if len(response.content)>2_000_000:
            raise ValueError('HTML artikel melebihi batas.')
    soup=BeautifulSoup(response.text,'html.parser')
    candidates=[]
    for key,attr in (('og:image','property'),('twitter:image','name'),
                     ('og:image:url','property'),('twitter:image:src','name')):
        for meta in soup.find_all('meta',attrs={attr:key}):
            url=urljoin(article_url,(meta.get('content') or '').strip())
            if url.startswith('https://') and url not in candidates:
                candidates.append(url)
    for url in candidates:
        parsed=urlparse(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.port not in (None,443):
            continue
        # Generic share/logo artwork is not an article image.
        lower=parsed.path.casefold()
        if any(word in lower for word in ('logo','favicon','default-share','placeholder','avatar','social-share')):
            continue
        if subject:
            # A page's og:image may be a generic social thumbnail (e.g. weather
            # over Antarctica for an IceCube neutrino story). Do not render an
            # unsubstantiated photo as if it were the actual scientific subject.
            descriptions=[]
            for tag,attr in (('og:image:alt','property'),('twitter:image:alt','name')):
                for meta in soup.find_all('meta',attrs={attr:tag}):
                    descriptions.append((meta.get('content') or '').strip())
            for img in soup.find_all('img'):
                linked=urljoin(article_url,img.get('src') or img.get('data-src') or '')
                if linked.split('?',1)[0] != url.split('?',1)[0]:
                    continue
                descriptions.append(img.get('alt') or '')
                figure=img.find_parent('figure')
                if figure:
                    caption=figure.find('figcaption')
                    if caption:
                        descriptions.append(caption.get_text(' ',strip=True))
            candidate={'title':Path(parsed.path).stem,
                       'description':' '.join(descriptions)}
            if not likely_same_subject(subject,candidate):
                continue
        return {'image_url':url,'original_url':url,'page_url':article_url,
                'title':(soup.title.get_text(' ',strip=True) if soup.title else 'Foto artikel sumber')[:160],
                'credit':None,'license':None,'license_url':None,
                'description':'Foto artikel sumber; wajib cek pemilik, kredit, lisensi, dan kesesuaian.'}
    return None


def plain(s):
    return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',s or ''))).strip()

def eligible_license(name):
    return bool(name and name.strip().lower() in {x.lower() for x in LICENSE_ALLOW})

def find_photos(query, limit=3, transport=None):
    """Returns candidate images; does NOT declare rights verified or photo relevance proven."""
    params={'action':'query','generator':'search','gsrsearch':f'filetype:bitmap {query[:100]}',
            'gsrnamespace':6,'gsrlimit':max(3,min(limit*4,30)),'prop':'imageinfo',
            'iiprop':'url|extmetadata|size|mime','iiurlwidth':1800,'format':'json'}
    with httpx.Client(timeout=25,follow_redirects=True,transport=transport,headers={'User-Agent':'UnfoundedTheoryEditorialBot/0.1 (media research)'}) as client:
        response=client.get(COMMONS_API,params=params)
        response.raise_for_status()
        pages=response.json().get('query',{}).get('pages',{})
    found=[]
    for page in pages.values():
        for info in page.get('imageinfo',[]):
            ext=info.get('extmetadata') or {}
            def val(k):return plain((ext.get(k) or {}).get('value',''))
            license_name=val('LicenseShortName')
            u=info.get('thumburl') or info.get('url') or ''
            if not eligible_license(license_name) or info.get('mime') not in ('image/jpeg','image/png','image/webp'):
                continue
            if info.get('width',0)<1050 or info.get('height',0)<650 or not u.startswith('https://'):
                continue
            found.append({'image_url':u,'original_url':info.get('url') or u,'page_url':info.get('descriptionurl',''),
              'license':license_name,'license_url':val('LicenseUrl'),
              'credit':val('Attribution') or val('Artist') or page.get('title',''),
              'title':plain(page.get('title','').removeprefix('File:')),
              'description':val('ImageDescription')[:600]})
            if len(found)>=limit:return found
    return found

def intake_image(url,output_path,transport=None):
    """Only HTTPS, no redirects, bounded bytes, verified raster decoding.

    Called exclusively with trusted Wikimedia API URLs or editor-supplied URLs.
    Never download into app server when URL might access local/private networks.
    """
    from ipaddress import ip_address
    from socket import getaddrinfo
    host=urlparse(url).hostname or ''
    parsed=urlparse(url)
    if parsed.scheme!='https' or not host or parsed.port not in (None,443):
        raise ValueError('Foto harus memakai URL HTTPS publik.')
    if host.lower() in {'localhost','metadata.google.internal'} or host.endswith(('.localhost','.local','.internal')):
        raise ValueError('Host privat tidak diperbolehkan.')
    # Ensure no private/loopback/link-local address is returned by DNS. HTTP redirect is disabled.
    if transport is None:
        for res in getaddrinfo(host,443,type=1):
            ip=ip_address(res[4][0])
            if not ip.is_global:raise ValueError('IP nonpublik tidak diperbolehkan.')
    else:
        # Tests can inject a transport but should never use it for arbitrary production URLs.
        if host not in ('upload.wikimedia.org','commons.wikimedia.org','example.org'):
            raise ValueError('Host uji tidak diizinkan')
    with httpx.Client(timeout=30,follow_redirects=False,transport=transport,headers={'User-Agent':'UnfoundedTheoryEditorialBot/0.1 (https://unfoundedtheory.vercel.app; editorial image retrieval)','Accept':'image/avif,image/webp,image/png,image/jpeg,*/*'}) as client:
        with client.stream('GET',url) as resp:
            resp.raise_for_status()
            if resp.headers.get('content-type','').split(';')[0].lower() not in ('image/jpeg','image/png','image/webp'):
                raise ValueError('URL bukan foto yang didukung.')
            blob=bytearray()
            for chunk in resp.iter_bytes():
                blob.extend(chunk)
                if len(blob)>15*1024*1024:raise ValueError('Foto melebihi batas 15 MB.')
    from io import BytesIO
    try:
        with Image.open(BytesIO(blob)) as im:
            if im.width*im.height>40_000_000:raise ValueError('Resolusi foto terlalu besar.')
            im=im.convert('RGB')
            target=Path(output_path);target.parent.mkdir(parents=True,exist_ok=True)
            im.save(target,format='JPEG',quality=94)
    except (UnidentifiedImageError,OSError) as exc:
        raise ValueError('File foto tidak valid.') from exc
    return str(target)

def render_draft(draft,source_path=None):
    from .renderer import render
    from .renderer import require_cover_fit
    require_cover_fit(draft.highlight, CONFIG.font_path)
    src=source_path or draft.source_image_path
    if not src or not Path(src).is_file():
        # On Vercel, previous /tmp files vanish; re-acquire approved source.
        src=str(Path(CONFIG.media_dir)/draft.id/f'source_v{draft.version}.jpg')
        origin=draft.source_image_url or ''
        if origin.startswith('https://'):
            intake_image(origin,src)
        elif origin.startswith('telegram-upload:') and CONFIG.telegram_token:
            from .telegram import TelegramClient
            TelegramClient(CONFIG.telegram_token).download_photo(origin.split(':',1)[1],src)
        else:
            raise ValueError('File foto sumber tidak tersedia; pilih foto lagi')
    out=Path(CONFIG.media_dir)/draft.id/f'v{draft.version}.jpg'
    # Make green emphasis survive automatic hook fitting, manual revisions and
    # imported drafts with stale or missing accent words.
    from .manual_hook import accent_for_hook
    draft.accent_words=accent_for_hook(draft.highlight,draft.accent_words)
    draft.image_local_path=render(src,draft.highlight,out,accent_words=draft.accent_words or [],
                      logo_path=CONFIG.brand_logo,font_path=CONFIG.font_path)
    if __import__('os').environ.get('VERCEL'):
        # Persist the immutable final render before returning from this invocation.
        draft.image_url=upload_public_jpeg(draft.image_local_path, f'{draft.id}/v{draft.version}.jpg')
    else:
        draft.image_url=None
    return draft.image_local_path

def upload_public_jpeg(local_path,object_key,transport=None):
    """Upload immutable rendered content to public Supabase Storage bucket. Admin sets bucket policies."""
    if not CONFIG.supabase_url or not CONFIG.supabase_key:
        raise RuntimeError('Supabase Storage belum dikonfigurasi')
    p=Path(local_path)
    if not p.exists():raise ValueError('Render JPEG tidak ditemukan')
    host=CONFIG.supabase_url.rstrip('/')
    if not host.startswith('https://'):raise ValueError('SUPABASE_URL harus HTTPS')
    import urllib.parse
    key=urllib.parse.quote(object_key,safe='/')
    bucket=urllib.parse.quote(CONFIG.media_bucket,safe='')
    endpoint=f'{host}/storage/v1/object/{bucket}/{key}'
    with httpx.Client(timeout=40,transport=transport) as client:
        r=client.post(endpoint,content=p.read_bytes(),headers={'Authorization':'Bearer '+CONFIG.supabase_key,
                     'apikey':CONFIG.supabase_key,'Content-Type':'image/jpeg','x-upsert':'false'})
        r.raise_for_status()
    return f'{host}/storage/v1/object/public/{bucket}/{key}'
