"""The planner is private, versioned and cannot schedule Meta publication."""
from dataclasses import replace
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from utbot.models import Base,make_engine,Story,Draft,Audit
from utbot import planner
from utbot.web import app
from utbot.research import fingerprint


def test_planner_private_calendar_and_manual_focus(monkeypatch):
    import os
    monkeypatch.setenv('PLANNER_PASSWORD','demo-strong-editor-password')
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(planner,'Session',Session)
    with Session() as db:
        url='https://science.nasa.gov/universe/fake-science-test/'
        s=Story(fingerprint=fingerprint(url),title='Observasi penting',
                source_name='NASA',source_url=url,topic='astronomy')
        db.add(s);db.flush()
        d=Draft(story_id=s.id,highlight='Teleskop Melihat Citra Unik Di Antariksa',
                caption='Sebuah temuan menarik.',hashtags=['#Sains'],
                source_image_url=None)
        db.add(d);db.commit();id=d.id
    client=TestClient(app,base_url='https://localhost')
    assert client.get('/planner/drafts').status_code==401
    assert client.post('/planner/login',json={'password':'wrong'}).status_code==401
    assert client.post('/planner/login',json={'password':'demo-strong-editor-password'}).status_code==200
    results=client.get('/planner/drafts').json()['drafts']
    assert len(results)==1
    assert results[0]['id']==id
    assert client.patch('/planner/drafts/'+id,json={'planned_at':'2026-10-20T12:00:00+07:00'}).status_code==200
    with Session() as db:
        d=db.get(Draft,id)
        assert d.scheduled_at is None, 'Planner must not invoke automatic Meta publishing'
        assert d.status=='pending_approval'
        assert db.query(Audit).filter_by(event='content_plan_changed').count()==1
    assert client.post('/planner/logout').status_code==200
    assert client.get('/planner/drafts').status_code==401


def test_website_root_is_content_studio():
    from app import app as root
    client=TestClient(root,follow_redirects=False)
    response=client.get('/')
    assert response.status_code==307
    assert response.headers['location']=='/api/planner'
