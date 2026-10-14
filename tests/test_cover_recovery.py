"""Real-article cover fallback must not falsely certify image rights."""
import httpx
import pytest
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft
from utbot.media import find_article_photo
from utbot.cover_recovery import recover_article_cover
from utbot.research import fingerprint

def test_exact_source_article_image_read_without_declaring_license():
    def handler(req):
        assert str(req.url)=='https://science.nasa.gov/space/mission-test/'
        return httpx.Response(200,text=(
            '<html><head><title>Mission test</title>'
            '<meta property="og:image" content="https://images-assets.nasa.gov/mission-test-hero.jpg">'
            '</head><body></body></html>'),headers={'content-type':'text/html'})
    data=find_article_photo('https://science.nasa.gov/space/mission-test/',
                            transport=httpx.MockTransport(handler))
    assert data['image_url']=='https://images-assets.nasa.gov/mission-test-hero.jpg'
    assert data['license'] is None and data['credit'] is None

def test_source_photo_recovery_revokes_prior_approval_and_requires_manual_rights(tmp_path):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        u='https://science.nasa.gov/space/mission-test/'
        st=Story(fingerprint=fingerprint(u),title='Mission test',source_url=u,
                 source_name='NASA',topic='space')
        db.add(st);db.flush()
        d=Draft(story_id=st.id,
                highlight='Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',
                caption='Sebuah peristiwa.\\n\\nIlmuwan memeriksa.\\n\\nNamun bukti terbatas.\\n\\nApa hasilnya?',
                hashtags=['#Sains','#Astronomi','#NASA','#Riset','#UnfoundedTheory'])
        db.add(d);db.flush()
        def intake(url,path):
            Path(path).parent.mkdir(parents=True,exist_ok=True)
            Path(path).write_bytes(b'preview placeholder for mocked renderer')
        def renderer(draft):
            draft.image_local_path=str(tmp_path/'cover.jpg')
            draft.image_url='https://example.org/unverified-preview.jpg'
        recover_article_cover(db,d,st,finder=lambda _url:{
            'image_url':'https://images-assets.nasa.gov/mission-test-hero.jpg',
            'page_url':u},intake=intake,renderer=renderer)
        assert d.version==2
        assert d.image_url and not d.rights_reviewed
        assert d.photo_license is None and d.image_credit is None
        assert d.media_page_url==u

def test_article_photo_rejects_untrusted_or_generic_logo():
    with pytest.raises(ValueError,match='sumber primer'):
        find_article_photo('https://untrusted.test/article/')
    response=httpx.MockTransport(lambda req:httpx.Response(200,text=(
        '<meta property="og:image" content="https://nasa.gov/logo-default-share.jpg">'),
        headers={'content-type':'text/html'}))
    assert find_article_photo('https://nasa.gov/news/',transport=response) is None


def test_official_photo_requires_specific_subject_not_just_location():
    # Antarctica alone is insufficient evidence for an IceCube neutrino image.
    wrong = httpx.MockTransport(lambda req: httpx.Response(
        200, text=('<html><head>'
                   '<meta property="og:image" content="https://images-assets.nasa.gov/antarctica-storm.jpg">'
                   '<meta property="og:image:alt" content="Snowstorm over Antarctica">'
                   '</head></html>'),
        headers={'content-type':'text/html'}))
    url='https://science.nasa.gov/space/icecube-neutrino/'
    assert find_article_photo(url,transport=wrong,
        subject='IceCube Neutrino Observatory in Antarctica') is None

    matching = httpx.MockTransport(lambda req: httpx.Response(
        200, text=('<html><head>'
                   '<meta property="og:image" content="https://images-assets.nasa.gov/icecube-detector.jpg">'
                   '<meta property="og:image:alt" content="IceCube neutrino detector observatory in Antarctica">'
                   '</head></html>'),
        headers={'content-type':'text/html'}))
    found=find_article_photo(url,transport=matching,
        subject='IceCube Neutrino Observatory in Antarctica')
    assert found and found['image_url'].endswith('icecube-detector.jpg')
