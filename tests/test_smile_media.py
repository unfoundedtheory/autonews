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
