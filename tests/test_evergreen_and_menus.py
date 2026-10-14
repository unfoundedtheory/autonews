"""Evergreen scientific discovery and compact Telegram callback regressions."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock

from sqlalchemy.orm import sessionmaker

from utbot.models import Base, make_engine, Story, Draft
from utbot.research import (
    discover, evergreen_sources, parse_source_response, fingerprint)
from utbot.telegram_ui import (
    pending_page, photo_candidate_message, photo_keyboard)
from utbot import web


def session():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def make_draft(index):
    return SimpleNamespace(id=str(uuid4()),version=1,
        highlight=f'Penemuan Lama di Bumi {index} \n yang Masih Membuat Ilmuwan Penasaran',
        photo_candidates=[])


def test_old_science_stories_are_admitted_without_age_cutoff():
    db=session()
    try:
        url='https://science.nasa.gov/universe/origin-of-galaxies/'
        feed=(f'<rss><channel><item><title>The Story of Ancient Galaxies</title>'
              f'<link>{url}</link>'
              '<pubDate>Tue, 01 Jan 2002 10:00:00 GMT</pubDate>'
              '</item></channel></rss>').encode()
        source={'name':'NASA history','url':'https://science.nasa.gov/feed/',
                'topic':'astronomy'}
        now=datetime(2026,10,14,tzinfo=timezone.utc)
        result=list(discover(db,sources=[source],
                             fetcher=lambda url:feed,now=now))
        assert result[0]['inserted']==1
        db.commit()
        story=db.query(Story).one()
        assert story.published_at.year==2002
        assert story.verification_status=='needs_fact_check'
        again=list(discover(db,sources=[source],
                            fetcher=lambda url:feed,now=now))
        assert again[0]['inserted']==0
        assert again[0]['duplicates']==1
    finally:
        db.close()


def test_future_dated_claim_is_rejected_even_though_archives_allowed():
    db=session()
    try:
        content=(b'<rss><channel><item><title>Future Event</title>'
                 b'<link>https://www.nasa.gov/future-science/</link>'
                 b'<pubDate>Mon, 01 Jan 2040 10:00:00 GMT</pubDate>'
                 b'</item></channel></rss>')
        feed={'name':'NASA','url':'https://www.nasa.gov/feed/',
              'topic':'science'}
        result=list(discover(db,sources=[feed],
                             fetcher=lambda url:content,
                             now=datetime(2026,10,14,tzinfo=timezone.utc)))
        assert result[0]['inserted']==0
        assert result[0]['excluded']==1
    finally:
        db.close()


def test_evergreen_sources_are_primary_and_rotated_daily():
    a=evergreen_sources(datetime(2026,10,14,tzinfo=timezone.utc))
    b=evergreen_sources(datetime(2026,10,15,tzinfo=timezone.utc))
    assert a[0]['url']!=b[0]['url']
    assert 'apod-basic' in a[0]['url']
    assert a[1]['topic']=='science'
    assert a[2]['topic']=='archaeology'
    assert all(item['url'].startswith('https://') for item in a)


def test_primary_archive_listing_strips_navigation_and_uses_only_articles():
    nasa=(b'<html><body><main>'
          b'<nav><h2><a href="/history/">NASA History</a></h2></nav>'
          b'<h3><a href="https://www.nasa.gov/apollo-discoveries-remembered/">'
          b'Apollo Discoveries That Changed Lunar Science</a></h3>'
          b'</main></body></html>')
    src={'format':'history_listing','url':'https://www.nasa.gov/history-news-and-articles/'}
    rows=parse_source_response(src,src['url'],nasa)
    assert len(rows)==1
    assert 'Apollo' in rows[0]['title']
    assert rows[0]['pub'] is None

    nature=(b'<html><body><main>'
            b'<h3><a href="/articles/s41586-026-00001">'
            b'Ancient Human Life in a Prehistoric Cave</a></h3>'
            b'<h3><a href="/subscribe">Subscribe to the newsletter</a></h3>'
            b'</main></body></html>')
    src={'format':'archaeology_listing','url':'https://www.nature.com/subjects/archaeology'}
    rows=parse_source_response(src,src['url'],nature)
    assert len(rows)==1
    assert rows[0]['url'].startswith('https://www.nature.com/articles/')


def test_pending_page_is_readable_and_paginates():
    records=[make_draft(i) for i in range(12)]
    text,menu=pending_page(records[:5],12,0)
    assert '\n1. ' in text and '\n5. ' in text
    assert r'\n' not in text
    assert 'Halaman 1/3' in text
    labels=[item['text'] for row in menu['inline_keyboard'] for item in row]
    assert all(len(s)<40 for s in labels)
    assert any('Berikutnya' in label for label in labels)
    assert not any('Sebelumnya' in label for label in labels)
    _,last=pending_page(records[10:],12,2)
    labels=[item['text'] for row in last['inline_keyboard'] for item in row]
    assert any('Sebelumnya' in label for label in labels)
    assert not any('Berikutnya' in label for label in labels)


def test_photo_choices_are_compact_and_include_real_source():
    d=make_draft(0)
    d.photo_candidates=[
        {'title':'Dr. Elisa Quintana NASA Mission Pandora-fig1.jpg',
         'license':'Public domain','credit':'NASA/JPL',
         'page_url':'https://commons.wikimedia.org/wiki/File:Elisa_Quintana.jpg'},
        {'title':'Eugene F Kranz at mission control.png','license':'CC BY 4.0',
         'credit':'NASA'},
    ]
    message=photo_candidate_message(d)
    assert '1. Dr. Elisa Quintana NASA Mission Pandora-fig1' in message
    assert '.jpg' not in message and '.png' not in message
    assert '\n   Kredit: NASA/JPL' in message
    assert '\n   Lisensi: Public domain' in message
    assert r'\n' not in message
    kb=photo_keyboard(d)['inline_keyboard']
    assert kb[0][0]['text']=='🔎 Lihat 1'
    assert kb[0][1]['text']=='✅ Pilih 1'
    assert kb[1][0]['text']=='✅ Pilih 2'
    assert kb[0][1]['callback_data'].startswith('pick0:')


def test_telegram_pending_navigation_shows_next_five(monkeypatch):
    from dataclasses import replace
    db=session()
    try:
        for i in range(12):
            url=f'https://science.nasa.gov/story/history-{i}/'
            st=Story(fingerprint=fingerprint(url),title='Science history',
                     source_url=url,source_name='NASA',topic='science')
            db.add(st);db.flush()
            db.add(Draft(story_id=st.id,
                         highlight=f'Sejarah Ilmuwan {i} Menjelaskan Alam Semesta',
                         caption='Sains dan sejarah',hashtags=[]))
        db.commit()
        bot=SimpleNamespace(messages=[],answers=[])
        bot.message=lambda chat,msg,kb=None:bot.messages.append((msg,kb))
        bot.answer=lambda *args:bot.answers.append(args)
        monkeypatch.setattr(web,'_bot',lambda:bot)
        monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,
                             admin_ids=frozenset({42})))
        update={'callback_query':{'id':'navcallback','from':{'id':42},
                'message':{'chat':{'id':123}},
                'data':'nav:pending:1'}}
        assert web.telegram_webhook(update,db=db)['ok']
        body,menu=bot.messages[0]
        assert 'Halaman 2/3' in body
        assert len([x for row in menu['inline_keyboard'] for x in row
                    if x['text'].startswith('👁 Buka')])==5
        assert r'\n' not in body
    finally:
        db.close()


def test_generate_test_news_tries_evergreen_when_latest_feed_exhausted(monkeypatch):
    db=session()
    try:
        calls=[]
        def fake_discover(db,sources=None):
            calls.append(sources)
            if sources and sources[0]['name']=='NASA APOD Archive':
                yield {'feed':'NASA APOD Archive','seen':25,'inserted':1}
            else:
                yield {'feed':'NASA latest','seen':175,'inserted':0,'duplicates':49}
        tries=[]
        def fake_prepare(db,limit,notifier):
            tries.append(True)
            if len(tries)==2:
                return [{'status':'prepared','has_photo':True}]
            return []
        monkeypatch.setattr('utbot.research.discover',fake_discover)
        monkeypatch.setattr(web,'prepare_batch',fake_prepare)
        monkeypatch.setenv('ENABLE_LIVE_PUBLISH','false')
        result=web.generate_test_news(db,None,123)
        assert '✅' in result
        assert len(calls)==2 and len(tries)==2
        assert calls[1][0]['name']=='NASA APOD Archive'
    finally:
        db.close()
