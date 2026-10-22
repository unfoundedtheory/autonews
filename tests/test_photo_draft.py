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
