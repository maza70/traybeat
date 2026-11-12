"""Icon input handling: theme names, image files, image bytes and PIL images (via Pillow)."""

from __future__ import annotations

import io
import os
from typing import Union

from PIL import Image

from .tb_status_notifier_item import Pixmap

PIXMAP_SIZES = (16, 22, 24, 32, 48, 64)
"""Square sizes generated for StatusNotifierItem pixmaps (never upscaled)."""

MAX_PIXMAP_SIZE = 128
"""Largest pixmap edge sent over D-Bus."""

MENU_ICON_SIZE = 32
"""Largest edge of PNG icons sent for menu items."""

IconSource = Union[str, "os.PathLike[str]", bytes, bytearray, memoryview, Image.Image, "TB_Icon"]
"""Anything accepted as icon: theme name, file path, image bytes, PIL image or TB_Icon."""


class TB_Icon:
    """An icon that is either a system theme name or an image; converts to what D-Bus needs."""

    def __init__(self, source: IconSource | None = None) -> None:
        """Resolve ``source``; a str is a file path if the file exists, otherwise a theme name."""
        self._name = ""
        self._image: Image.Image | None = None
        self._pixmap_cache: list[Pixmap] | None = None
        self._png_cache: dict[int, bytes] = {}

        if source is None:
            return
        if isinstance(source, TB_Icon):
            self._name = source._name
            self._image = source._image
        elif isinstance(source, str):
            self._from_string(source)
        elif isinstance(source, (bytes, bytearray, memoryview)):
            self._image = self._load(io.BytesIO(bytes(source)))
        elif isinstance(source, Image.Image):
            self._image = self._square(source.convert("RGBA"))
        else:
            self._image = self._load(os.fspath(source))

    @classmethod
    def of(cls, source: IconSource | None) -> TB_Icon:
        """Return ``source`` itself if it already is a TB_Icon, otherwise convert it."""
        return source if isinstance(source, TB_Icon) else cls(source)

    @property
    def name(self) -> str:
        """Return the system icon name ("" if the icon is an image)."""
        return self._name

    @property
    def has_image(self) -> bool:
        """Return True if the icon holds image data."""
        return self._image is not None

    @property
    def is_empty(self) -> bool:
        """Return True if neither a name nor an image is set."""
        return not self._name and self._image is None

    def to_pixmaps(self) -> list[Pixmap]:
        """Return ARGB32 pixmaps in several sizes for StatusNotifierItem (empty for theme names)."""
        if self._image is None:
            return []
        if self._pixmap_cache is None:
            side = self._image.width
            target = min(side, MAX_PIXMAP_SIZE)
            sizes = sorted({size for size in PIXMAP_SIZES if size < target} | {target})
            self._pixmap_cache = [self._to_argb(self._resized(self._image, size)) for size in sizes]
        return self._pixmap_cache

    def to_png(self, size: int = MENU_ICON_SIZE) -> bytes:
        """Return PNG bytes scaled down to at most ``size`` pixels (empty for theme names)."""
        if self._image is None:
            return b""
        if size not in self._png_cache:
            buffer = io.BytesIO()
            self._resized(self._image, size).save(buffer, format="PNG", optimize=True)
            self._png_cache[size] = buffer.getvalue()
        return self._png_cache[size]

    # ------------------------------------------------------------------ internals

    def _from_string(self, text: str) -> None:
        """Treat ``text`` as file path if it exists, otherwise as theme icon name."""
        path = os.path.expanduser(text)
        if os.path.isfile(path):
            self._image = self._load(path)
        elif os.sep in text:
            raise FileNotFoundError(f"Icon file not found: {text}")
        else:
            self._name = text

    @classmethod
    def _load(cls, source: str | io.BytesIO) -> Image.Image:
        """Open an image file or buffer and return it as square RGBA."""
        with Image.open(source) as opened:
            return cls._square(opened.convert("RGBA"))

    @staticmethod
    def _square(image: Image.Image) -> Image.Image:
        """Center the image on a transparent square canvas."""
        width, height = image.size
        if width == height:
            return image
        side = max(width, height)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(image, ((side - width) // 2, (side - height) // 2))
        return canvas

    @staticmethod
    def _resized(image: Image.Image, size: int) -> Image.Image:
        """Scale the image down to ``size`` (never up)."""
        if image.width <= size:
            return image
        return image.resize((size, size), Image.Resampling.LANCZOS)

    @staticmethod
    def _to_argb(image: Image.Image) -> Pixmap:
        """Convert an RGBA image to (width, height, ARGB32 bytes)."""
        red, green, blue, alpha = image.split()
        return (image.width, image.height, Image.merge("RGBA", (alpha, red, green, blue)).tobytes())
