"""Indonesia-first science discovery without abandoning primary-source verification."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from utbot.models import Base, Draft, Story, make_engine
from utbot.research import (
    SOURCES, candidate_priority, discover, fingerprint,
    is_indonesia_space_story, parse_brin_listing, sort_candidates)
from utbot.editorial import trusted_source
from utbot import pipeline


def db_session():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine,expire_on_commit=False)()


def test_official_brin_space_listings_filter_generic_and_off_domain_articles():
    page=b"""
    <html><main>
      <article><h3>BRIN Ungkap Jejak Benda Antariksa di Langit Kalimantan</h3>
        <a href="/news/130999/brin-ungkap-jejak-benda-antariksa">Selengkapnya</a></article>
      <article><a href="https://www.brin.go.id/orpa/posts/kabar/cuaca-antariksa-indonesia">
        Cuaca Antariksa di Indonesia Dipantau Peneliti BRIN</a></article>
      <article><a href="/news/130888/brin-kembangkan-pertanian">BRIN Kembangkan Pupuk Organik Lokal</a></article>
      <article><a href="https://example.com/news/131000/meteor">
        Meteor jatuh di Jawa Timur, katanya!</a></article>
      <article><a href="/news/130999/brin-ungkap-jejak-benda-antariksa">
        BRIN Ungkap Jejak Benda Antariksa di Langit Kalimantan</a></article>
    </main></html>"""
    results=parse_brin_listing(page)
    assert len(results)==2
    assert all(trusted_source(row['url']) for row in results)
    assert all(row['pub'] is None for row in results)
    assert results[0]['url'].startswith('https://brin.go.id/news/130999/')
    assert results[1]['url'].startswith('https://www.brin.go.id/orpa/posts/kabar/')
    assert not any('Pupuk' in row['title'] for row in results)


def test_brin_listing_without_server_side_article_links_fails_closed():
    with pytest.raises(ValueError,match='Listing BRIN'):
        parse_brin_listing('<html><div id="app"></div></html>')
    assert any(src['name']=='BRIN Indonesia Space' for src in SOURCES)
    assert any('orpa/posts/kabar' in src['url'] for src in SOURCES)


def test_discovery_accepts_brin_primary_and_retains_fact_check_gate():
    html=b'<html><article><a href="/news/130999/antariksa-di-kalimantan">' + (
        b'BRIN Teliti Fenomena Antariksa di Langit Kalimantan') + b'</a></article></html>'
    feeds=[{'name':'BRIN Indonesia Space','url':'https://brin.go.id/news',
            'format':'brin_listing','topic':'space'}]
    db=db_session()
    try:
        rows=list(discover(db,sources=feeds,fetcher=lambda url:html,
                           now=datetime(2026,10,21,tzinfo=timezone.utc)))
        assert rows[0]['inserted']==1
        db.commit()
        story=db.query(Story).one()
        assert story.verification_status=='needs_fact_check'
        assert story.topic=='space'
        assert is_indonesia_space_story(story)
        assert list(discover(db,sources=feeds,fetcher=lambda url:html))[0]['duplicates']==1
    finally:
        db.close()


def test_local_space_headlines_rank_above_global_and_unrelated_local_news():
    older=datetime(2026,10,18,tzinfo=timezone.utc)
    recent=datetime(2026,10,21,tzinfo=timezone.utc)
    items=[
        SimpleNamespace(title='BRIN Mengembangkan Teknologi Pertanian di Indonesia',
                        topic='science',source_name='BRIN Indonesia',published_at=recent,
                        created_at=recent,id='unrelated'),
        SimpleNamespace(title='NASA Observes a New Galaxy Using Space Telescope',
                        topic='astronomy',source_name='NASA',published_at=recent,
                        created_at=recent,id='global'),
        SimpleNamespace(title='Fenomena Meteor Terlihat di Langit Kalimantan',
                        topic='space',source_name='NASA',published_at=older,
                        created_at=older,id='local'),
    ]
    assert [x.id for x in sort_candidates(items)]==['local','global','unrelated']
    assert [candidate_priority(item) for item in items]==[2,1,0]
    assert not is_indonesia_space_story(items[0])
    assert not is_indonesia_space_story(SimpleNamespace(
        title='Indonesia Tingkatkan Hasil Panen',source_name='BRIN'))


def test_pipeline_attempts_older_indonesian_space_story_first(monkeypatch):
    db=db_session()
    try:
        nasa='https://science.nasa.gov/universe/galaxy-discovery/'
        brin='https://brin.go.id/news/130999/antariksa-kalimantan'
        global_story=Story(fingerprint=fingerprint(nasa),title='NASA Discovers Distant Galaxy',
                           source_url=nasa,source_name='NASA',topic='astronomy',
                           published_at=datetime(2026,10,21,tzinfo=timezone.utc))
        local_story=Story(fingerprint=fingerprint(brin),
                          title='BRIN Temukan Jejak Meteor di Langit Kalimantan',
                          source_url=brin,source_name='BRIN Indonesia Space',topic='space',
                          published_at=datetime(2026,10,19,tzinfo=timezone.utc))
        db.add_all([global_story,local_story]);db.commit()
        attempted=[]
        def fake_prepare(session,story):
            attempted.append(story.id)
            d=Draft(story_id=story.id,highlight='Berita sains',
                    caption='Data riset',hashtags=['#Sains'])
            session.add(d);session.flush()
            return d
        monkeypatch.setattr(pipeline,'prepare_story',fake_prepare)
        outcome=pipeline.prepare_batch(db,limit=1)
        assert len(outcome)==1 and outcome[0]['status']=='prepared'
        assert attempted==[local_story.id]
    finally:
        db.close()
