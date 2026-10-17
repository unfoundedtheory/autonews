"""Telegram preview does not repeat the highlight already printed in the cover."""
from types import SimpleNamespace
from utbot.telegram import preview_text,send_preview


def test_preview_text_is_caption_only():
    draft=SimpleNamespace(highlight='HIGHLIGHT UNIK YANG TIDAK BOLEH DI CHAT',
        caption='Isi caption untuk publikasi Instagram.',
        hashtags=['#NASA','#Astronomi','#Sains','#Antariksa','#UnfoundedTheory'],
        image_local_path=None,image_url='https://example.org/cover.jpg',
        image_credit=None,photo_license=None,media_page_url=None)
    content=preview_text(draft,None)
    assert 'HIGHLIGHT UNIK YANG TIDAK BOLEH DI CHAT' not in content
    assert not content.startswith('HIGHLIGHT')
    assert 'Isi caption untuk publikasi Instagram.' in content


def test_preview_keeps_cover_and_editorial_buttons(monkeypatch):
    draft=SimpleNamespace(id='1',version=1,status='pending_approval',
        publish_state='unpublished',approved_by=None,
        highlight='HIGHLIGHT UNIK YANG TIDAK BOLEH DI CHAT',
        caption='Isi caption untuk publikasi Instagram.',
        hashtags=['#NASA','#Astronomi','#Sains','#Antariksa','#UnfoundedTheory'],
        image_local_path=None,image_url='https://example.org/cover.jpg',
        image_credit=None,photo_license=None,media_page_url=None,
        source_image_url=None,last_error=None)
    class Bot:
        def __init__(self):self.photos=[];self.messages=[]
        def photo(self,*args):self.photos.append(args)
        def message(self,*args):self.messages.append(args)
    bot=Bot()
    send_preview(bot,123,draft,None)
    assert len(bot.photos)==1
    assert len(bot.messages)==1
    assert bot.messages[0][2]['inline_keyboard']
    assert 'HIGHLIGHT UNIK YANG TIDAK BOLEH DI CHAT' not in bot.messages[0][1]
