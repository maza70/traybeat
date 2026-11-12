import io
import logging
import threading
import uuid
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageFile

from traybeat.core.tb_config import TB_EntryType, TB_StationEntry
from traybeat.core.tb_cover_fetch import TB_CoverFetch
from traybeat.gui.tb_resource import TB_Resource
from traybeat.lib.tb_const import TEMP_PATH
from traybeat.lib.tb_i_core import TB_Meta

MetadataChangedCallback = Callable[["TB_MetaCollector"], None]


@dataclass
class TB_MetaCoverData:
    mimetype: str
    cover: bytes


class TB_MetaCollector:
    _logger = logging.getLogger(__name__)
    TB_META_COVER_DATA: str = "TB_META_COVER_DATA"

    @property
    def current_meta(self) -> TB_Meta:
        return self._current_meta

    def __init__(self, on_meta_change: MetadataChangedCallback, collectTimeout: float = 1, tempDir: Path = TEMP_PATH) -> None:
        """constructor

        Args:
            on_meta_change (MetadataChangedCallback): callback when meta is changed
            collectTimeout (float, optional): how long wait to collect the first meta . Defaults to 1.
            tempDir (Path, optional): the temp ir to write the covers. Defaults to Path(tempfile.gettempdir()).
        """

        self._temp_dir: Path
        self._cover_file_png: Path
        self._current_cover_file: Path | None = None
        self._startup_collect_time: threading.Timer | None = None
        self._tag_clear_timer: threading.Timer | None = None
        self._startup_collect_lock = threading.Lock()
        self._on_meta_change: MetadataChangedCallback
        self._collect_Timeout: float

        self._current_meta: TB_Meta = TB_Meta()
        self._startup_meta: TB_Meta | None = None
        self._currentStation: TB_StationEntry | None = None
        self._cover_fetch: TB_CoverFetch = TB_CoverFetch(lambda cover: self._onCover(cover))
        self._on_meta_change = on_meta_change
        self._collect_Timeout = collectTimeout
        self._temp_dir = tempDir
        self._current_cover_file: Path | None
        self._current_cover_file: Path | None

    def _startup_collect(self) -> None:
        self._logger.debug("startup collector")

        with self._startup_collect_lock:
            # Vorhandenen Timer abbrechen
            if self._startup_collect_time is not None:
                self._startup_collect_time.cancel()

            # Neuen Timer starten
            self._startup_collect_time = threading.Timer(
                interval=self._collect_Timeout,
                function=self._on_startup_collect_finish,
            )
            self._startup_collect_time.daemon = True
            self._startup_collect_time.start()

    def _on_startup_collect_finish(self) -> None:
        self._logger.debug("startup collector finish")
        with self._startup_collect_lock:
            self._startup_collect_time = None

        if self._startup_meta is not None:
            if self._startup_meta.cover_file == "":
                self.set_cover(self._startup_meta, None, None)
            self._current_meta = self._startup_meta
        self._startup_meta = None
        self._notify_metaChange()

    def _extract_cover_bytes(self, value: Any) -> bytes | None:
        """Extract encoded image bytes from a GStreamer image tag."""
        try:
            # GStreamer normally represents image tags as Gst.Sample.
            buffer = value.get_buffer() if hasattr(value, "get_buffer") else value
            if buffer is None or not hasattr(buffer, "get_size"):
                return None

            size = buffer.get_size()
            if size <= 0:
                return None

            data = buffer.extract_dup(0, size)
            return bytes(data) if data else None
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None

    def _onCover(self, cover: ImageFile.ImageFile):
        try:
            cover.thumbnail((240, 240), Image.Resampling.LANCZOS)
            image: Image.Image = cover
            if cover.mode in ("CMYK", "P"):
                image = cover.convert("RGBA" if "transparency" in cover.info else "RGB")

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            if self._startup_meta is not None:
                self.set_cover(self._startup_meta, "image/png", buffer.getvalue())
            else:
                self.set_cover(self._current_meta, "image/png", buffer.getvalue())
                self._notify_metaChange()

        except Exception:
            self._logger.exception("can't save cover")

    def set_cover(self, collectMeta: TB_Meta, mimetype: str | None, image_data: bytes | None):
        if self._currentStation is None:
            return
        guid = str(uuid.uuid4())

        self._unlinkCover()

        if image_data is None or mimetype not in ("image/png", "image/jpeg"):
            self._logger.debug("set generic cover")
            collectMeta.cover_mimetype = mimetype or "image/png"
            self._current_cover_file = Path(self._temp_dir, f"{guid}.png")
            if self._currentStation.type == TB_EntryType.PLAYLIST:
                self._current_cover_file.write_bytes(TB_Resource.get_bytes("png", "cover_mp3.png"))
            else:
                self._current_cover_file.write_bytes(TB_Resource.get_bytes("png", "cover_webradio.png"))

            collectMeta.is_generic_cover = True
        else:
            collectMeta.cover_mimetype = mimetype or "image/jpg"
            if mimetype == "image/png":
                self._current_cover_file = Path(self._temp_dir, f"{guid}.png")
            elif mimetype == "image/jpeg":
                self._current_cover_file = Path(self._temp_dir, f"{guid}.jpg")
            with open(self._current_cover_file, "wb") as f:
                f.write(image_data)
        collectMeta.cover_file = str(self._current_cover_file)
        self._logger.debug(f"write cover file {collectMeta.cover_file}")

    def _notify_metaChange(self):

        if self._on_meta_change is not None:
            self._logger.debug("notify, meta is changed")
            self._on_meta_change(self)

    def _unlinkCover(self):
        if self._current_cover_file is not None and self._current_cover_file.exists():
            self._current_cover_file.unlink()
            self._current_cover_file = None

    def set_favicon(self, collectMeta: TB_Meta):
        # we hav no cover for the stream check when we get the location the favicon of the main page
        if collectMeta.location != "" and collectMeta.is_generic_cover:
            if self._currentStation and self._currentStation.imageUrl is None:
                self._cover_fetch.fetch_location(collectMeta.location)

    def _add_meta(self, collectMeta: TB_Meta, tag_name: str, data: list[Any]) -> bool:
        try:
            # self._logger.debug(f"new meta {tag_name}")
            if tag_name not in ("title", "organization", "artist", "image", "preview-image", "location"):
                return False

            # Image tags contain Gst.Sa collectMeta.locationmple objects, not plain metadata.
            # Extract their encoded image bytes and keep them out of the
            # regular metadata dictionary.
            if tag_name in {"image", "preview-image"}:
                for image_value in data:
                    caps = image_value.get_caps() if hasattr(image_value, "get_caps") else None
                    cover_mimetype = "image/jpeg"  # default
                    if caps and not caps.is_empty():
                        cover_mimetype = cover_mimetype = caps.to_string().split(",", 1)[0].split(",", 1)[0]

                    image_data = self._extract_cover_bytes(image_value)
                    if image_data:
                        self.set_cover(collectMeta, cover_mimetype, image_data)
                        return True

            value: Any = data[0] if len(data) == 1 else data
            if isinstance(value, (str, int, float, bool)) or value is None:
                normalized = value
            else:
                normalized = str(value)
            self._logger.debug(f"new meta {tag_name}={normalized!s}")
            match tag_name:
                case "location":
                    if collectMeta.location != normalized:
                        collectMeta.location = str(normalized)
                        self.set_favicon(collectMeta)
                        return True
                case "artist":
                    if collectMeta.artist != normalized:
                        collectMeta.artist = str(normalized)
                        return True
                case "title":
                    if collectMeta.title != normalized:
                        artist, _, title = str(normalized).partition(" - ")
                        if title != "":
                            changed = collectMeta.artist != artist or collectMeta.title != title
                            collectMeta.title = title
                            collectMeta.artist = artist
                            return changed
                        else:
                            collectMeta.title = str(normalized)
                            return True
                case _:
                    return False
            return False
        except Exception:
            self._logger.exception(f"Error on get meta attribute:{tag_name}")
            return False

    def new_song(self, station: TB_StationEntry):
        self._currentStation = deepcopy(station)
        self._startup_meta = TB_Meta(artist="- na -", title="- na -")
        if self._currentStation.imageUrl is not None:
            _ = self._cover_fetch.fetch(self._currentStation.imageUrl)
        self._startup_collect()  # keep time to collect metas before clear the old

    def _update_tags(self, collectMeta: TB_Meta, tags: Any):
        is_changed = False
        for i in range(tags.n_tags()):
            name = tags.nth_tag_name(i)
            values: list[Any] = []
            for j in range(tags.get_tag_size(name)):
                try:
                    value = tags.get_value_index(name, j)
                    values.append(value)
                except (TypeError, ValueError):
                    continue
            if not values:
                continue
            is_changed = self._add_meta(collectMeta, name, values) or is_changed
        return is_changed

    def update_meta(self, name: str, data: list[Any]):
        """update one meta value
        Args:
            name (str): name of the meta field
            data (list[Any]): data of the meta field
        """
        if self._startup_meta is not None:
            self._add_meta(self._startup_meta, name, data)
        else:
            if self._add_meta(self._current_meta, name, data):
                self._notify_metaChange()

    def update(self, tags: Any):
        """update meta from the gstreamer player

        Args:
            tags (Any): tag from the gstreamer
        """
        if self._startup_meta is not None:
            self._update_tags(self._startup_meta, tags)
        else:
            if self._update_tags(self._current_meta, tags):
                self._notify_metaChange()
