# pyright: reportPrivateUsage=false
import shutil
from pathlib import Path
from typing import Any

from typing_extensions import override

from traybeat.core.tb_config import TB_EntryType, TB_StationEntry
from traybeat.core.tb_meta_collector import TB_MetaCollector


class TestableMetaCollector(TB_MetaCollector):
    @override
    def _startup_collect(self):
        pass


class FakeTags:
    def __init__(self, data: dict[str, list[Any]]):
        self.data = data

    def n_tags(self):
        return len(self.data)

    def nth_tag_name(self, index: int):
        return list(self.data.keys())[index]

    def get_tag_size(self, name: str):
        return len(self.data[name])

    def get_value_index(self, name: str, index: int):
        return self.data[name][index]


class FakeBuffer:
    def __init__(self, data: bytes):
        self.data = data

    def get_size(self):
        return len(self.data)

    def extract_dup(self, offset, size):  # type: ignore
        return self.data[offset : offset + size]


class FakeCover:
    def __init__(self, data: bytes, mimetype: str = "image/jpeg"):
        self.buffer = FakeBuffer(data)
        self.mimetype = mimetype

    def get_buffer(self):
        return self.buffer

    def get_caps(self):
        return FakeCaps(self.mimetype)


class FakeCaps:
    def __init__(self, mimetype: str):
        self.mimetype = mimetype

    def is_empty(self):
        return False

    def get_structure(self, index: int):
        return FakeStructure(self.mimetype)


class FakeStructure:
    def __init__(self, name: str):
        self.name = name

    def get_name(self):
        return self.name


def test_meta_collect_webradio():

    update_called: int = 0

    def updatemeta(collector: TB_MetaCollector):
        nonlocal update_called
        update_called += 1

    filepath = Path(__file__).resolve().parent
    tempDir = Path(filepath, "../files/temp/test_meta_collect_webradio")
    shutil.rmtree(tempDir, ignore_errors=True)
    tempDir.mkdir(parents=True, exist_ok=True)

    subject = TestableMetaCollector(on_meta_change=lambda collector: updatemeta(collector), tempDir=tempDir)
    station = TB_StationEntry(type=TB_EntryType.WEBRADIO, caption="TestRadio", url="http://traybeat")
    subject.new_song(station)
    subject._on_startup_collect_finish()  # fake time
    # ok we have no tags collected
    assert update_called == 1
    assert subject.current_meta.title == "- na -"
    assert subject.current_meta.artist == "- na -"
    assert subject.current_meta.cover_file.endswith(".png")

    tags = FakeTags(
        {
            "title": ["TestRadio"],
        }
    )
    subject.update(tags)
    assert update_called == 2
    assert subject.current_meta.title == "TestRadio"

    tags = FakeTags(
        {
            "title": ["traybeat - player"],
        }
    )
    subject.update(tags)
    assert update_called == 3
    assert subject.current_meta.artist == "traybeat"
    assert subject.current_meta.title == "player"
    assert subject.current_meta.cover_mimetype == "image/png"
    assert subject.current_meta.cover_file.endswith(".png")
    assert Path(subject.current_meta.cover_file).exists()


def test_meta_collect_playlist():
    update_called: int = 0

    def updatemeta(collector: TB_MetaCollector):
        nonlocal update_called
        update_called += 1

    filepath = Path(__file__).resolve().parent
    tempDir = Path(filepath, "../files/temp/test_meta_collect_playlist")
    shutil.rmtree(tempDir, ignore_errors=True)
    tempDir.mkdir(parents=True, exist_ok=True)

    subject = TestableMetaCollector(on_meta_change=lambda collector: updatemeta(collector), tempDir=tempDir)
    station = TB_StationEntry(type=TB_EntryType.PLAYLIST, caption="Test-Playlist", path="/home/traybeat/top100.m3u")
    subject.new_song(station)
    tags = FakeTags(
        {
            "title": ["test"],
            "artist": ["TrayBeat"],
        }
    )
    subject.update(tags)
    assert subject.current_meta.title == ""
    assert subject.current_meta.artist == ""
    assert subject.current_meta.cover_file == ""
    subject._on_startup_collect_finish()  # fake timer
    assert update_called == 1
    assert subject.current_meta.title == "test"
    assert subject.current_meta.artist == "TrayBeat"
    assert subject.current_meta.cover_file.endswith(".png")

    image_data = b"\x89"
    sample = FakeCover(image_data, "image/jpeg")
    tags = FakeTags(
        {
            "image": [sample],
        }
    )
    subject.update(tags)
    assert update_called == 2
    assert subject.current_meta.title == "test"
    assert subject.current_meta.artist == "TrayBeat"
    assert subject.current_meta.cover_file.endswith(".jpg")
    assert Path(subject.current_meta.cover_file).stat().st_size == 1

    # new song in playlist with no tags
    update_called = 0
    subject.new_song(station)  # this song has no tags
    subject._on_startup_collect_finish()  # fake timer
    assert update_called == 1
    assert subject.current_meta.title != ""
    assert subject.current_meta.artist != ""
    assert subject.current_meta.cover_file.endswith(".png")  # default cover

    # new song in playlist with tags
    subject.new_song(station)  # this song has no tags
    tags = FakeTags(
        {
            "title": ["test"],
            "artist": ["TrayBeat"],
            "image": [sample],
        }
    )
    subject.update(tags)
    subject._on_startup_collect_finish()  # fake timer
    assert update_called == 2
    assert subject.current_meta.title == "test"
    assert subject.current_meta.artist == "TrayBeat"
    assert subject.current_meta.cover_file.endswith(".jpg")
