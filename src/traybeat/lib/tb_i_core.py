from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path

from traybeat.core.tb_config import TB_EntryType, TB_StationEntry, TB_StationsConfig
from traybeat.lib.tb_const import TEMP_PATH


class TB_CorePlayerState(StrEnum):
    ERROR = auto()
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()
    UNKNOWN = auto()


@dataclass
class TB_CorePlayerInfo:
    station: TB_StationEntry | None = None
    state: TB_CorePlayerState = TB_CorePlayerState.STOPPED
    error: str = ""
    playlist_index: int = 0
    playlist_length: int = 0
    playlist_song_position: float = 0
    volume: int = 0
    volume_gain: int = 0

    @property
    def isPlayList(self) -> bool:
        if self.station is not None:
            return self.station.type == TB_EntryType.PLAYLIST
        else:
            return False


@dataclass
class TB_CorePlayerMeta:
    title: str = ""
    artist: str = ""
    cover_mimetype: str = ""
    cover_file: str = ""


@dataclass
class TB_Meta:
    _cover_file_jpg: Path = Path(TEMP_PATH, "tray-beat-cover.jpg")
    _cover_file_png: Path = Path(TEMP_PATH, "tray-beat-cover.png")
    location: str = ""
    title: str = ""
    artist: str = ""
    _cover_mimetype: str = ""
    _cover_file: str = ""
    _is_generic_cover: bool = False

    @property
    def is_generic_cover(self) -> bool:
        return self._is_generic_cover

    @is_generic_cover.setter
    def is_generic_cover(self, value: bool):
        self._is_generic_cover = value

    @property
    def cover_mimetype(self) -> str:
        return self._cover_mimetype

    @cover_mimetype.setter
    def cover_mimetype(self, value: str):
        self._cover_mimetype = value

    @property
    def cover_file(self) -> str:
        return self._cover_file

    @cover_file.setter
    def cover_file(self, value: str):
        self._cover_file = value

    @property
    def cover_url(self) -> str:
        return f"file://{self._cover_file}"


@dataclass
class PlayerChangedData:
    meta: TB_CorePlayerMeta | None = None
    player_info: TB_CorePlayerInfo | None = None


OnCorePlayerChanged = Callable[[PlayerChangedData], None]


class TB_I_Core(ABC):
    """Interface for a media player."""

    @property
    @abstractmethod
    def current_station(self) -> TB_StationEntry | None:
        """the current station."""

    @abstractmethod
    def quit(self) -> None:
        """quit TrayBeat."""

    @abstractmethod
    def player_play(self) -> None:
        """Start playback."""

    @abstractmethod
    def player_play_station(self, station_id: str) -> None:
        """Start playback with a given station."""

    @abstractmethod
    def player_toogle_pause(self) -> None:
        """Pause playback."""

    @abstractmethod
    def player_stop(self) -> None:
        """stop playback."""

    @abstractmethod
    def player_next(self) -> None:
        """next Track/webradio."""

    @abstractmethod
    def player_previous(self) -> None:
        """previous track/webradio."""

    @abstractmethod
    def player_volume_step(self, delta: int) -> None:
        """increment or decrement the volume"""

    @abstractmethod
    def player_set_volume(self, volume: int) -> None:
        """set the volume from 0 to 100%"""

    @abstractmethod
    def player_get_volume(self) -> int:
        """get current volume from 0 to 100%"""

    @abstractmethod
    def player_stations(self) -> TB_StationsConfig:
        """get all configured stations"""

    @abstractmethod
    def player_meta(self) -> TB_CorePlayerMeta:
        """get the current meta"""

    @abstractmethod
    def player_info(self) -> TB_CorePlayerInfo:
        """get the current player state"""

    @abstractmethod
    def player_changed_subscribe(self, onchanged: OnCorePlayerChanged):
        """notify if state or meta is changed"""

    @abstractmethod
    def player_changed_unsubscribe(self, onchanged: OnCorePlayerChanged):
        """notify if state or meta is changed"""
