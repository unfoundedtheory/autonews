"""Rejecting a manual story offers vetted options without AI generation."""
from types import SimpleNamespace
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft,Audit
from utbot.research import fingerprint
from utbot.automation_mode import set_mode
from utbot.replacements import available_replacements,offer_replacements,validate_selection
from utbot.telegram import manual_post_keyboard


def test_replacement_choices_exclude_rejected_or_already_drafted():
    eng=make_engine('sqlite://')
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng,expire_on_commit=False)() as db:
        url='https://science.nasa.gov/rejected/'
        old=Story(fingerprint=fingerprint(url),title='Rejected news',source_url=url,
                  source_name='NASA',topic='space')
        db.add(old);db.flush()
        d=Draft(story_id=old.id,highlight='Original',caption='Caption',hashtags=[],
                status='rejected')
        db.add(d)
        for idx in range(5):
            link=f'https://science.nasa.gov/replacement-{idx}/'
            db.add(Story(fingerprint=fingerprint(link),title=f'New science idea {idx}',
                         source_url=link,source_name='NASA',topic='science'))
        db.commit()
        set_mode(db,'manual_post',42)
        sent=[]
        bot=SimpleNamespace(message=lambda chat,text,keyboard:sent.append((text,keyboard)))
        first=offer_replacements(db,d,42,bot,123,discover_if_empty=False)
        assert len(first)==4
        assert len({x.id for x in first})==4
        assert all(x.id != old.id for x in first)
        assert 'PILIH BERITA PENGGANTI' in sent[0][0]
        assert all('Buat Berita' in str(item) for item in sent[0][1]['inline_keyboard'][:4])
        assert validate_selection(db,first[0].id,42).id==first[0].id
        second=offer_replacements(db,d,42,bot,123,discover_if_empty=False)
        assert len(second)==1
        assert second[0].id not in {x.id for x in first}
        draft=Draft(story_id=first[0].id,highlight='A second draft',
                    caption='Caption',hashtags=[])
        db.add(draft);db.commit()
        try:
            validate_selection(db,first[0].id,42)
        except ValueError:
            pass
        else:
            raise AssertionError('Drafted candidate was offered twice')


def test_manual_keyboard_has_reject_and_no_approval():
    d=SimpleNamespace(id='x',version=1,status='pending_approval',
                      publish_state='unpublished',image_url='https://example.com/cover.jpg',
                      image_local_path=None)
    labels=[button.get('callback_data','').split(':')[0]
            for row in manual_post_keyboard(d)['inline_keyboard'] for button in row]
    assert 'reject' in labels and 'manualdone' in labels
    assert not {'approve','postnow','retryig'}.intersection(labels)
