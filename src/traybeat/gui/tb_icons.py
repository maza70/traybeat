from enum import Enum, auto
from pathlib import Path

from traybeat.gui.tb_resource import TB_Resource


class TB_IconsName(Enum):
    TRAY_PLAY = auto()
    TRAY_STOP = auto()
    TRAY_PAUSE = auto()
    TRAY_ERROR = auto()
    PLAY = auto()
    PAUSE = auto()
    STOP = auto()
    MUTE = auto()
    QUIT = auto()
    FOLDER = auto()
    PLAYLIST = auto()
    WEBRADIO = auto()
    CONFIG = auto()
    INFO = auto()
    MUSIC = auto()


class TB_Icons:
    def __init__(self, icon_theme: str):

        self._icons: dict[TB_IconsName, Path | str]
        self._icons = {
            TB_IconsName.STOP: TB_Resource.get_path(f"png/{icon_theme}", "stop.png"),
            TB_IconsName.PLAY: TB_Resource.get_path(f"png/{icon_theme}", "play.png"),
            TB_IconsName.QUIT: TB_Resource.get_path(f"png/{icon_theme}", "exit.png"),
            TB_IconsName.FOLDER: TB_Resource.get_path(f"png/{icon_theme}", "folder.png"),
            TB_IconsName.CONFIG: TB_Resource.get_path(f"png/{icon_theme}", "edit.png"),
            TB_IconsName.INFO: TB_Resource.get_path(f"png/{icon_theme}", "info.png"),
            TB_IconsName.MUSIC: TB_Resource.get_path(f"png/{icon_theme}", "music.png"),
            TB_IconsName.TRAY_STOP: TB_Resource.get_path("png", "traybeat_stop.png"),
            TB_IconsName.TRAY_PLAY: TB_Resource.get_path("png", "traybeat_play.png"),
            TB_IconsName.TRAY_ERROR: TB_Resource.get_path("png", "traybeat_error.png"),
            TB_IconsName.TRAY_PAUSE: TB_Resource.get_path("png", "traybeat_pause.png"),
            TB_IconsName.WEBRADIO: TB_Resource.get_path(f"png/{icon_theme}", "webradio.png"),
            TB_IconsName.PLAYLIST: TB_Resource.get_path(f"png/{icon_theme}", "playlist.png"),
            TB_IconsName.PAUSE: TB_Resource.get_path(f"png/{icon_theme}", "pause.png"),
        }

    def GetBytes(self, icon: TB_IconsName) -> bytes:
        iconResource = self._icons[icon]
        return TB_Resource.get_bytes("", str(iconResource))

    def GetIcon(self, icon: TB_IconsName) -> str:
        iconResource = self._icons[icon]
        return str(iconResource)
