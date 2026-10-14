"""Regression tests for feed URL migrations, broken XML and discovery diagnostics."""
from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import sessionmaker
from utbot.models import Base, make_engine, Story
from utbot.research import SOURCES, parse_items, discover
from utbot import web, research


def make_db():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_apod_uses_new_nasa_feed():
    assert SOURCES[0]['url'].startswith('https://science.nasa.gov/wp-json/wp/v2/apod-basic')
    assert 'https://science.nasa.gov/feed/apod-basic/' in SOURCES[0]['fallback_urls']
    assert not any(s['url']=='https://apod.nasa.gov/apod.rss' for s in SOURCES)


def test_malformed_nasa_rss_recovers_entry_but_not_untrusted_url():
    xml=b'''<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0"><channel><title>NASA Science</title>
    <item><title>Galaxy mission update</title>
    <link>https://science.nasa.gov/galaxy-mission/</link>
    <pubDate>Tue, 13 Oct 2026 10:00:00 GMT</pubDate>
    <description>Science & discovery</description></item></channel></rss>'''
    result=parse_items(xml)
    assert result[0]['url']=='https://science.nasa.gov/galaxy-mission/'
    assert result[0]['pub']==datetime(2026,10,13,10,tzinfo=timezone.utc)


def test_html_redirect_and_broken_xml_not_disguised_as_empty_feed():
    with pytest.raises(ValueError,match='bukan RSS/Atom|bukan feed RSS/Atom'):
        parse_items(b'<html><body>NASA APOD web landing page</body></html>')
    with pytest.raises(ValueError):
        parse_items(b'<rss><channel><item><title>broken')


def test_feed_dtd_is_blocked():
    with pytest.raises(ValueError,match='DTD|entity'):
        parse_items(b'<!DOCTYPE rss [<!ENTITY x "example">]><rss><channel/></rss>')
    with pytest.raises(ValueError,match='DTD'):
        parse_items(b'<!DOCTYPE rss SYSTEM "https://evil.test/malicious.dtd"><rss><channel/></rss>')
    assert parse_items(b'<!DOCTYPE rss><rss><channel/></rss>')==[]


def test_failure_in_one_official_feed_does_not_block_others():
    db=make_db()
    bad={'name':'NASA Bad XML','url':'https://science.nasa.gov/feed/','topic':'space'}
    good={'name':'NASA Good RSS','url':'https://www.nasa.gov/news-release/feed/','topic':'space'}
    ok=b'<rss><channel><item><title>A science discovery</title><link>https://www.nasa.gov/a-science-discovery/</link><pubDate>Tue, 13 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
    try:
        result=list(discover(db,sources=[bad,good],now=datetime(2026,10,13,11,tzinfo=timezone.utc),
                             fetcher=lambda u: b'<html>landing page</html>' if 'science.nasa.gov' in u else ok))
        assert 'error' in result[0]
        assert result[1]['inserted']==1
        assert db.query(Story).count()==1
    finally:
        db.close()


def test_telegram_reports_feed_outages_separately_from_no_news(monkeypatch):
    db=make_db()
    try:
        monkeypatch.setattr(web,'prepare_batch',lambda *a,**k: [])
        monkeypatch.setattr(research,'discover',lambda db,sources:iter([
            {'feed':'NASA APOD','error':'HTML instead of XML','inserted':0},
            {'feed':'ESA','inserted':0,'seen':5,'duplicates':5}]))
        monkeypatch.setenv('ENABLE_LIVE_PUBLISH','false')
        text=web.generate_test_news(db,None,123)
        assert 'feed bermasalah' in text and '1 feed yang berhasil' in text
        monkeypatch.setattr(research,'discover',lambda db,sources:iter([
            {'feed':'NASA APOD','error':'HTML instead of XML','inserted':0}]))
        assert 'semua feed resmi bermasalah' in web.generate_test_news(db,None,123)
    finally:
        db.close()


def test_apod_wordpress_api_parses_official_json_and_no_random_hosts():
    import json
    from utbot.research import parse_apod_json
    example=[{'title':{'rendered':'A Galaxy &amp; a Nebula'},
              'link':'https://science.nasa.gov/apod/2026-10-13-test/',
              'date_gmt':'2026-10-13T09:00:00'},
             {'title':{'rendered':'Untrusted'},'link':'https://evil.test/story'}]
    items=parse_apod_json(json.dumps(example).encode())
    assert len(items)==1
    assert items[0]['title']=='A Galaxy & a Nebula'
    assert items[0]['pub']==datetime(2026,10,13,9,tzinfo=timezone.utc)


def test_eso_public_listing_replaces_400_feed_without_scraping_undated_links():
    from utbot.research import parse_eso_listing
    doc=b'''<html><article>
        <h3><a href="/public/news/eso2619/">New evidence near Jupiter</a></h3>
        <time>13 October 2026</time>
        </article><article><a href="/public/news/eso2510/">Very old discovery</a>
        <span>12 June 2025</span></article>
        <p><a href="/public/news/eso2618/">Undated entry</a></p></html>'''
    items=parse_eso_listing(doc)
    assert len(items)==2
    assert items[0]['url']=='https://www.eso.org/public/news/eso2619/'
    assert items[0]['pub']==datetime(2026,10,13,tzinfo=timezone.utc)


def test_nasa_science_falls_back_to_working_official_nasa_rss():
    db=make_db()
    source=next(s for s in SOURCES if s['name']=='NASA Science')
    valid=b'<rss><channel><item><title>NASA telescope data</title><link>https://www.nasa.gov/science/example/</link><pubDate>Tue, 13 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
    calls=[]
    def fetch(url):
        calls.append(url)
        return b'<html>not RSS</html>' if url==source['url'] else valid
    try:
        rows=list(discover(db,sources=[source],fetcher=fetch,now=datetime(2026,10,14,tzinfo=timezone.utc)))
        assert rows[0]['fallback_used'] is True and rows[0]['inserted']==1
        assert calls==[source['url'],'https://www.nasa.gov/feed/']
    finally:db.close()
