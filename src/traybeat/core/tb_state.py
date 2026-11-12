import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dacite import Config, from_dict

from traybeat.core.tb_config import TB_EntryType, TB_StationEntry
from traybeat.lib.tb_const import STATE_PATH
from traybeat.lib.tb_exception import TB_Exception
from traybeat.lib.tb_player import PlayerStatus


@dataclass
class TB_StationState:
    playlist_index: int = 0
    playlist_song_pos: float = 0


@dataclass
class TB_TrayBeatState:
    playerVolume: int = 100
    lastStationId: str = ""
    stationStates: dict[str, TB_StationState] = field(default_factory=dict[str, TB_StationState])


class TB_State:
    _logger = logging.getLogger(__name__)
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        STATE_PATH.mkdir(parents=True, exist_ok=True)
        self._stateFile = Path(STATE_PATH, "state.json")
        self._state = self._load()
        self._initialized = True
        self._instance = self

    @property
    def tray_beat_state(self) -> TB_TrayBeatState:
        return self._state

    def get_station_state(self, stationId: str) -> TB_StationState:
        state = self._state.stationStates.get(stationId)
        if state is None:
            return TB_StationState()
        return state

    def update_station_state(self, station: TB_StationEntry, playerState: PlayerStatus):
        self._state.lastStationId = station.uniqueId
        if station.type == TB_EntryType.PLAYLIST:
            self._state.stationStates[station.uniqueId] = TB_StationState(
                playlist_index=playerState.playlist_index, playlist_song_pos=playerState.playlist_song_position
            )

    def _load(self) -> TB_TrayBeatState:
        if self._stateFile.exists():
            try:
                self._logger.debug(f"Load state from {self._stateFile}")
                data = json.loads(self._stateFile.read_text(encoding="utf-8"))
                return from_dict(
                    data_class=TB_TrayBeatState,
                    data=data,
                    config=Config(
                        check_types=True,
                        strict=False,
                    ),
                )
            except Exception as exc:
                raise TB_Exception(f"Can't read State {self._stateFile}, error: {exc}")
        else:
            return TB_TrayBeatState()

    def save(self):
        self._logger.debug(f"Save state to {self._stateFile}")
        with open(self._stateFile, "w", encoding="utf-8") as stateFile:
            json.dump(asdict(self._state), stateFile, indent=2)
