import shutil
from pathlib import Path

from gi.repository import Gio, GLib  # type: ignore


class TB_Util:
    @staticmethod
    def trim(text: str, max_len: int) -> str:
        """trim a text to the maximum length inclusive the three points."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    @staticmethod
    def copy_to_clipboard(text: str) -> bool:
        """Copy text to the clipboard via KDE's Klipper (no extra packages)."""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            bus.call_sync(
                "org.kde.klipper",
                "/klipper",
                "org.kde.klipper.klipper",
                "setClipboardContents",
                GLib.Variant("(s)", (text,)),
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
            return True
        except GLib.Error:
            return False

    @staticmethod
    def del_directory_content(directory: Path):
        for item in directory.iterdir():
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
