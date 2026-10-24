"""Ensure cover fallback works when primary media providers fail."""
from types import SimpleNamespace
import httpx
from utbot.photo_sources import discover_cover_candidates


def test_source_search_tries_nasa_and_openverse_if_article_and_commons_fail():
    story=SimpleNamespace(
        title="NASA JPL Looks to Next 90 Years of Innovation Exploration",
        source_url="https://www.nasa.gov/some-news/"
    )
    calls=[]
    def unavailable(*args,**kwargs):
        calls.append("unavailable")
        raise httpx.HTTPStatusError("403",request=httpx.Request("GET","https://example.org/"),
                                   response=httpx.Response(403))
    def nasa(term,limit=8):
        calls.append("nasa")
        return []
    def openverse(term,limit=8):
        calls.append("openverse")
        return [{"image_url":"https://images.example.org/jpl.jpg",
                 "title":"NASA JPL innovation and exploration 90 years",
                 "description":"JPL innovation and exploration laboratory",
                 "credit":"Example author","license":None}]
    found,errors=discover_cover_candidates(
        story, source_finder=lambda *a,**k: None,
        nasa_search=nasa, commons_search=unavailable,
        openverse_search=openverse, max_variants=2)
    assert found and found[0]["source"]=="openverse"
    assert "commons:http_403" in errors
    assert "nasa" in calls and "openverse" in calls


def test_alternatives_reject_unrelated_generic_photo():
    story=SimpleNamespace(
        title="WD J1330 6435 Green Star",
        source_url="https://science.nasa.gov/image-article/example/"
    )
    unrelated={"image_url":"https://images.example.org/unrelated.jpg",
               "title":"Old tax record in census archive",
               "description":"Genealogy register district"}
    found,_=discover_cover_candidates(
        story,source_finder=lambda *a,**k: None,
        nasa_search=lambda *a,**k: [unrelated],
        commons_search=lambda *a,**k: [],
        openverse_search=lambda *a,**k: [],max_variants=1)
    assert found==[]
