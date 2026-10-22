import httpx
import pytest
from utbot.photos import nasa_photo_candidates
from utbot.drafter import extract_article_text

def test_nasa_photos_need_licenses():
    def handler(req):
        assert req.url.host=="images-api.nasa.gov"
        return httpx.Response(200,json={"collection":{"items":[{"data":[{"title":"Webb photo","nasa_id":"NASA-1","center":"GSFC"}],"links":[{"href":"https://images-assets.nasa.gov/image.jpg","render":"image"}]}]}})
    a=nasa_photo_candidates("webb",transport=httpx.MockTransport(handler))
    assert a[0]["license_status"]=="needs_rights_review"

def test_nontrusted_article_url_blocked():
    with pytest.raises(ValueError,match="allowlisted"):
        extract_article_text("https://evil.example/steal")

def test_article_extract_text():
    html='<html><article>'+''.join(f'<p>This is a sufficiently long sample NASA mission scientific paragraph number {i}, with detailed findings.</p>' for i in range(8))+'</article></html>'
    transport=httpx.MockTransport(lambda req:httpx.Response(200,text=html,headers={"content-type":"text/html"}))
    text=extract_article_text("https://www.nasa.gov/test/article",transport=transport)
    assert "paragraph number 7" in text


def test_photo_picker_always_offers_manual_upload_even_when_no_candidates():
    from types import SimpleNamespace
    from utbot.telegram_ui import photo_keyboard
    d=SimpleNamespace(id='id-1',version=2,photo_candidates=[])
    actions=[b['callback_data'] for row in photo_keyboard(d)['inline_keyboard']
             for b in row if 'callback_data' in b]
    assert 'photoupload:id-1:2' in actions
    assert 'photosearch:id-1:2' in actions


def test_photo_picker_offers_multiple_candidates_and_owner_upload():
    from types import SimpleNamespace
    from utbot.telegram_ui import photo_keyboard
    photos=[{'title':f'Slide {i}','page_url':f'https://commons.wikimedia.org/wiki/File:{i}'} for i in range(4)]
    d=SimpleNamespace(id='id-1',version=3,photo_candidates=photos)
    actions=[b.get('callback_data') for row in photo_keyboard(d)['inline_keyboard'] for b in row]
    assert all(f'pick{i}:id-1:3' in actions for i in range(4))
    assert 'photoupload:id-1:3' in actions

def test_telegram_photo_replacement_does_not_request_credit_or_license(monkeypatch):
    """A successful upload finishes the session and immediately sends the preview."""
    from dataclasses import replace
    from sqlalchemy.orm import sessionmaker
    from utbot.models import Base, make_engine, Story, Draft, TelegramSession
    from utbot import web
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    class Bot:
        def __init__(self): self.messages=[]
        def download_photo(self,file_id,path): return path
        def message(self,chat_id,text,reply_markup=None): self.messages.append(text)
    bot=Bot()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42})))
    monkeypatch.setattr(web,'_replace_telegram_photo',
        lambda db,d,file_id,uid,bot: setattr(d,'version',d.version+1))
    monkeypatch.setattr(web,'send_editor_preview',
        lambda db,bot,chat_id,d,st:bot.message(chat_id,'Preview baru'))
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        st=Story(title='NASA science',fingerprint='a'*64,
            source_url='https://science.nasa.gov/',source_name='NASA')
        db.add(st);db.flush()
        d=Draft(story_id=st.id,highlight='NASA science',caption='text',hashtags=[])
        db.add(d);db.flush()
        db.add(TelegramSession(user_id='42',draft_id=d.id,mode='photo',version=d.version))
        db.commit()
        out=web.telegram_webhook({'message':{
            'from':{'id':42},'chat':{'id':123},
            'photo':[{'file_id':'abc','width':1200,'height':1600}]}},db=db)
        assert out['photo_replaced']==d.id
        assert db.get(TelegramSession,'42') is None
        assert 'Preview baru' in bot.messages
        assert not any('Balas dua baris' in m or 'Lisensi: Public domain' in m
                       for m in bot.messages)
