import os
import shutil
import sys
import threading
import traceback
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

    @staticmethod
    def get_package_format() -> str:
        if os.environ.get("FLATPAK_ID"):
            return "flatpak"

        if os.environ.get("APPIMAGE"):
            return "appimage"

        return "system"

    @staticmethod
    def dump_threads() -> None:
        print("\n" + "=" * 70)
        print("ACTIVE THREADS")
        print("=" * 70)

        frames = sys._current_frames()  # type: ignore

        for thread in threading.enumerate():
            print(f"\nThread:    {thread.name}")
            print(f"Class:     {type(thread).__name__}")
            print(f"Module:    {type(thread).__module__}")
            print(f"Ident:     {thread.ident}")
            print(f"Native ID: {thread.native_id}")
            print(f"Daemon:    {thread.daemon}")
            print(f"Alive:     {thread.is_alive()}")

            ident = thread.ident
            frame = frames.get(ident) if ident is not None else None

            if frame is not None:
                print("Stack:")
                traceback.print_stack(frame)
            else:
                print("No Python stack available.")
