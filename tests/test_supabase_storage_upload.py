"""Storage must use POST for a new immutable asset, not PUT (overwrite)."""
from types import SimpleNamespace

import httpx
from utbot import media

def test_upload_new_render_uses_post_and_correct_public_url(tmp_path, monkeypatch):
    jpg = tmp_path / "post.jpg"
    jpg.write_bytes(b"JPEGDATA")
    monkeypatch.setattr(media, "CONFIG", SimpleNamespace(
        supabase_url="https://sampleproject.supabase.co",
        supabase_key="test-service-key",
        media_bucket="unfounded-media",
    ))
    def check(request):
        assert request.method == "POST"
        assert request.url.path == "/storage/v1/object/unfounded-media/draft-123/v1.jpg"
        assert request.headers["x-upsert"] == "false"
        assert request.headers["content-type"] == "image/jpeg"
        assert request.content == b"JPEGDATA"
        return httpx.Response(200, json={"Key": "unfounded-media/draft-123/v1.jpg"})
    result = media.upload_public_jpeg(
        jpg, "draft-123/v1.jpg", transport=httpx.MockTransport(check)
    )
    assert result == (
        "https://sampleproject.supabase.co/storage/v1/object/"
        "public/unfounded-media/draft-123/v1.jpg"
    )
