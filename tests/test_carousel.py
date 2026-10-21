"""Carousel layout, API semantics, flexible count and WIB daily limit."""
from datetime import datetime, timezone
from pathlib import Path
import pytest
import httpx
from PIL import Image
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft
from utbot.instagram import InstagramPublisher
from utbot.carousel import require_slide_set,validate_daily_limit,API_MAX_SLIDES


def draft(db,n=2):
    story=Story(fingerprint='f'+str(db.query(Story).count()),title='NASA image',
        source_url='https://science.nasa.gov/',source_name='NASA',
        verification_status='verified')
    db.add(story);db.flush()
    d=Draft(story_id=story.id,highlight='Penemuan NASA Mengungkap Fenomena Langit',
       caption='Keterangan.',hashtags=['#NASA'],
       post_format='carousel',carousel_slides=[
          {'image_url':f'https://example.org/{i}.jpg','caption':f'Fakta foto {i}'}
          for i in range(n)])
    db.add(d);db.flush()
    return d


def test_flexible_count_and_api_ceiling():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        assert len(require_slide_set(draft(db,2),for_api=True))==2
        assert len(require_slide_set(draft(db,10),for_api=True))==10
        with pytest.raises(ValueError,match='maksimal 10'):
            require_slide_set(draft(db,11),for_api=True)


def test_wib_day_limit_including_published():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        existing=draft(db,2)
        existing.status='published';existing.publish_state='published'
        existing.scheduled_at=datetime(2026,10,22,0,0,tzinfo=timezone.utc)
        new=draft(db,4)
        db.flush()
        with pytest.raises(ValueError,match='tanggal WIB'):
            validate_daily_limit(db,new,datetime(2026,10,22,8,0,tzinfo=timezone.utc))
        validate_daily_limit(db,new,datetime(2026,10,23,0,0,tzinfo=timezone.utc))


def test_graph_carousel_payload_and_image_items():
    received=[]
    def fake(req):
        received.append((req.url.path,dict(httpx.QueryParams(req.content.decode()))))
        return httpx.Response(200,json={'id':str(100+len(received))})
    pub=InstagramPublisher('https://graph.facebook.com','v24.0','999','fake',
                           transport=httpx.MockTransport(fake))
    children=[pub.create_carousel_child('https://example.org/a.jpg'),
              pub.create_carousel_child('https://example.org/b.jpg')]
    pub.create_carousel_container(children,'Ringkasan berita')
    assert received[0][1]['is_carousel_item']=='true'
    assert received[2][1]['media_type']=='CAROUSEL'
    assert received[2][1]['children']==','.join(children)


def test_carousel_cover_keeps_single_layout_untouched(tmp_path):
    from utbot.renderer import render_carousel_cover, BADGE_BOX
    original=tmp_path/'source.jpg';result=tmp_path/'cover.jpg'
    Image.new('RGB',(1400,1800),'#526274').save(original)
    render_carousel_cover(original,'NASA Mengungkap Fenomena Langit Tak Terduga',result)
    assert result.exists()
    with Image.open(result) as im:
        assert im.size==(1080,1350)
    assert BADGE_BOX==(402,900,678,948)
