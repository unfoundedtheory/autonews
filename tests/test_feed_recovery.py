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
    assert SOURCES[0]['url']=='https://science.nasa.gov/feed/apod-basic/'
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
    with pytest.raises(ValueError,match='DTD'):
        parse_items(b'<!DOCTYPE rss [<!ENTITY x "example">]><rss><channel/></rss>')


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
