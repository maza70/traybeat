import pytest
from PIL import ImageFile

from traybeat.core.tb_cover_fetch import TB_CoverFetch


@pytest.mark.asyncio
async def test_fetch_url():
    mime_type = ""
    size = [0, 0]

    def onCover(cover: ImageFile.ImageFile):
        nonlocal mime_type, size
        mime_type = cover.get_format_mimetype()
        size = cover.size

    subject = TB_CoverFetch(on_cover=lambda cover: onCover(cover))
    await subject.fetch_async("https://www.radioton.de/storage/thumbs/192x192/r:1693564697/95010.png")
    assert mime_type != ""
    assert size[0] > 0
    assert size[1] > 0


@pytest.mark.asyncio
async def test_fetch_favicon():
    mime_type = ""
    size = [0, 0]

    def onCover(cover: ImageFile.ImageFile):
        nonlocal mime_type, size
        mime_type = cover.get_format_mimetype()
        size = cover.size

    subject = TB_CoverFetch(on_cover=lambda cover: onCover(cover))
    await subject.fetch_location_async("https://www.antenne1.de/")
    assert mime_type != ""
    assert size[0] > 0
    assert size[1] > 0
