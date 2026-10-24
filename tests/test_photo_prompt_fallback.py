"""Photo action must not spam; alternatives use all configured image providers."""
from dataclasses import replace
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft
from utbot import web

def setup(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine,expire_on_commit=False)()
    st=Story(fingerprint='a'*64,title='NASA JPL innovation and exploration',source_name='NASA',
             source_url='https://www.nasa.gov/example/')
    db.add(st);db.flush()
    d=Draft(story_id=st.id,highlight='NASA JPL invention',caption='hello',hashtags=[])
    db.add(d);db.commit()
    class Bot:
        def __init__(self):self.messages=[]
        def answer(self,*args):pass
        def message(self,*args):self.messages.append(args)
    bot=Bot()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42})))
    def send(action,update):
        return web.telegram_webhook({'update_id':update,'callback_query':{
            'id':str(update),'from':{'id':42},'message':{'chat':{'id':9}},
            'data':f'{action}:{d.id}:{d.version}'}},db=db)
    return db,d,bot,send

def test_photo_action_is_quiet_while_same_session_active(monkeypatch):
    db,d,bot,send=setup(monkeypatch)
    try:
        assert send('photo',101)['awaiting']=='photo_or_url'
        size=len(bot.messages)
        assert send('photo',102)['unchanged'] is True
        assert len(bot.messages)==size
    finally:db.close()

def test_photo_search_uses_multiple_sources_and_does_not_require_license(monkeypatch):
    db,d,bot,send=setup(monkeypatch)
    try:
        from utbot import photo_sources
        calls=[]
        def discover(story):
            calls.append(story.title)
            return ([{'source':'openverse','image_url':'https://images.example.org/jpl.jpg',
                      'page_url':'https://example.org/jpl','title':'NASA JPL innovation',
                      'description':'JPL exploration','credit':None,'license':None}],['commons:http_403'])
        monkeypatch.setattr(photo_sources,'discover_cover_candidates',discover)
        result=send('photosearch',103)
        assert result['count']==1
        assert d.photo_candidates[0]['source']=='openverse'
        assert calls==[ 'NASA JPL innovation and exploration' ]
        assert any('Pilih Foto Cover' in str(m) for m in bot.messages)
    finally:db.close()
