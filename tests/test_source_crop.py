"""Any source photo orientation is cropped to a full-bleed 4:5 cover.

The source URL does not have to serve a 4:5 image. The fade fully hides
the last row of the source photograph behind opaque black at the bottom.
"""
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from utbot.media import intake_image
from utbot.renderer import render

HEADLINE=('Kota Berpenduduk Dua Juta Jiwa Lumpuh Saat Asap Pekat '
          'Selimuti Hutan Hujan Tropis')

@pytest.mark.parametrize('dims',[(1600,900),(900,1600),(900,900),(1200,800)])
def test_arbitrary_https_source_is_full_bleed_four_by_five_with_black_edge(tmp_path,dims):
    input_img=Image.new('RGB',dims,'#839bb1')
    data=BytesIO()
    input_img.save(data,'JPEG',quality=95)
    payload=data.getvalue()
    def handler(req):
        assert req.url.host=='example.org'
        return httpx.Response(200,headers={'content-type':'image/jpeg'},content=payload)
    src=tmp_path/'source.jpg'
    assert Path(intake_image('https://example.org/owner-photo.jpg',src,
                    transport=httpx.MockTransport(handler))).is_file()
    out=tmp_path/'cover.jpg'
    render(src,HEADLINE,out)
    with Image.open(out) as cover:
        assert cover.size==(1080,1350)
        # Top retains source image (no black bars / letterbox).
        assert max(cover.getpixel((10,20)))>100
        # Bottom is fully black even when source is bright, no visible seam.
        for point in ((2,1348),(540,1348),(1078,1348)):
            assert max(cover.getpixel(point))<=5

def test_square_source_crop_remains_aspect_correct():
    from utbot.renderer import _place_photo
    square=Image.new('RGB',(900,900),'white')
    output=_place_photo(square,(0.5,0.43))
    assert output.size==(1080,1350)
