"""Regression coverage for ESA/CAS SMILE discovery and 4:5 image workflow."""
import httpx
from utbot.media import find_photos,eligible_license
from utbot.photo_relevance import search_queries,likely_same_subject

def test_smile_search_prioritizes_distinctive_mission():
    queries=search_queries('Smile spacecraft solar wind magnetosphere ionosphere link explorer ESA CAS')
    assert queries[0]=='Smile spacecraft'
    assert len(queries)<=4
    assert all(len(q)<=100 for q in queries)

def test_smile_igo_license_and_landscape_candidate():
    assert eligible_license('CC BY-SA 3.0 IGO')
    assert not eligible_license('All rights reserved')
    def handler(request):
        assert 'Smile' in request.url.params['gsrsearch']
        return httpx.Response(200,json={'query':{'pages':{'101':{
            'title':'File:Smile spacecraft (artist impression) ESA501293.png',
            'imageinfo':[{'mime':'image/png','width':7680,'height':4320,
             'url':'https://upload.wikimedia.org/real.png',
             'thumburl':'https://upload.wikimedia.org/thumb/real.png',
             'descriptionurl':'https://commons.wikimedia.org/wiki/File:Smile_spacecraft.png',
             'extmetadata':{
               'LicenseShortName':{'value':'CC BY-SA 3.0 IGO'},
               'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/3.0/igo/'},
               'ImageDescription':{'value':'SMILE mission spacecraft artist impression'},
               'Artist':{'value':'European Space Agency'}}}]}}}})
    items=find_photos('Smile spacecraft',limit=3,transport=httpx.MockTransport(handler))
    assert len(items)==1
    assert items[0]['license']=='CC BY-SA 3.0 IGO'
    assert likely_same_subject('Smile spacecraft',items[0])
    assert 'impression' in items[0]['title'].lower()
    assert items[0]['image_url'].startswith('https://')

def test_wide_1600_x_900_not_filtered():
    def handler(_):
        return httpx.Response(200,json={'query':{'pages':{'12':{
         'title':'File:Smile spacecraft.jpg',
         'imageinfo':[{'mime':'image/jpeg','width':1600,'height':900,
          'thumburl':'https://upload.wikimedia.org/thumb.jpg',
          'descriptionurl':'https://commons.wikimedia.org/wiki/File:Smile_spacecraft.jpg',
          'extmetadata':{'LicenseShortName':{'value':'CC BY-SA 3.0 IGO'}}}]}}}})
    assert len(find_photos('Smile spacecraft',transport=httpx.MockTransport(handler)))==1

def test_retry_cover_button_requires_editor_selection(monkeypatch):
    from utbot.models import Base,make_engine,Story,Draft
    from sqlalchemy.orm import sessionmaker
    from utbot import web
    from dataclasses import replace
    from utbot.research import fingerprint
    from utbot.telegram import advanced_keyboard
    db=sessionmaker(bind=(eng:=make_engine('sqlite://')),expire_on_commit=False)()
    Base.metadata.create_all(eng)
    st=Story(fingerprint=fingerprint('https://www.esa.int/News/Smile'),
             title='SMILE spacecraft reveals new data',source_url='https://www.esa.int/News/Smile',
             source_name='ESA',topic='space')
    db.add(st);db.flush()
    dr=Draft(story_id=st.id,highlight='Cara Perisai Bumi Menahan Angin Matahari Masih Menyimpan Misteri',
             caption='Ilmuwan meneliti magnetosfer.\\n\\nESA menjelaskan.\\n\\nNamun temuannya belum final.\\n\\nApa selanjutnya?',
             hashtags=['#ESA','#Sains','#Space','#Bumi','#UnfoundedTheory'])
    db.add(dr);db.commit()
    assert any(x['callback_data'].startswith('retrycover:')
               for line in advanced_keyboard(dr)['inline_keyboard'] for x in line)
    class Bot:
        def __init__(self):self.messages=[]
        def answer(self,*args):pass
        def message(self,chat,text,reply_markup=None):self.messages.append((text,reply_markup))
    bot=Bot()
    from utbot import media
    photo={'image_url':'https://upload.wikimedia.org/Smile.jpg','title':'Smile spacecraft illustration',
           'page_url':'https://commons.wikimedia.org/wiki/File:Smile.jpg','credit':'ESA',
           'license':'CC BY-SA 3.0 IGO','license_url':'https://creativecommons.org/licenses/by-sa/3.0/igo/'}
    monkeypatch.setattr(media,'find_photos',lambda query,limit=6:[photo])
    monkeypatch.setattr(web,'_bot',lambda:bot)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42})))
    cb={'callback_query':{'id':'cb','from':{'id':42},'message':{'chat':{'id':9}},
         'data':f'retrycover:{dr.id}:{dr.version}'}}
    assert web.telegram_webhook(cb,db=db)['ok']
    assert dr.photo_candidates[0]['license']=='CC BY-SA 3.0 IGO'
    assert not dr.image_local_path and not dr.rights_reviewed
    assert any('Pilih satu kandidat cover' in s for s,m in bot.messages)
    db.close()

def test_source_resolution_600_fallback_and_below_600_rejected():
    def fetch_with_size(side):
        def handler(_):
            return httpx.Response(200,json={'query':{'pages':{'1':{
                'title':'File:Smile spacecraft.png',
                'imageinfo':[{'mime':'image/png','width':side,'height':1000,
                    'url':'https://upload.wikimedia.org/Smile.png',
                    'descriptionurl':'https://commons.wikimedia.org/wiki/File:Smile.png',
                    'extmetadata':{'LicenseShortName':{'value':'CC0'}}}]
            }}}})
        return find_photos('Smile spacecraft',transport=httpx.MockTransport(handler))
    assert fetch_with_size(590)==[]
    candidate=fetch_with_size(620)[0]
    assert candidate['resolution_review']=='conditional'
    assert fetch_with_size(760)[0]['resolution_review']=='standard'
