import copy
import json
import logging as _logging
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from dacite import Config, from_dict

from traybeat.lib.tb_const import CONFIG_PATH
from traybeat.lib.tb_exception import TB_Exception
from traybeat.lib.tb_i_core import TB_StationEntry, TB_StationsConfig, TB_StationType


class TB_Config:
    _logger = _logging.getLogger(__name__)

    def __init__(self) -> None:
        self._stationsConfig: TB_StationsConfig
        self._appConfigFile: Path
        self._stationsFile: Path
        self._stationFlatList: dict[str, TB_StationEntry] = {}
        self._stationsFile = Path(CONFIG_PATH, "stations.json")

    @property
    def AppConfigFile(self) -> Path:
        return self._appConfigFile

    @property
    def StationsFile(self) -> Path:
        return self._stationsFile

    @property
    def StationsConfig(self) -> TB_StationsConfig:
        return self._stationsConfig

    def initialize(self) -> None:
        self._stationsFile = Path(CONFIG_PATH, "stations.json")
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)

    def load_StationsConfig(self):
        self._logger.info(f"Load stations config from:{self._stationsFile}")
        if not self._stationsFile.exists():
            self._logger.info("No stations config found create one from defaults.")
            self._stationsConfig = copy.deepcopy(INIT_STATIONS)
        else:
            self._stationsConfig = self._load_StationsConfig(self._stationsFile)
        if self._validateStationConfig(self._stationsConfig):
            # stations ar changed by the check (uuid added)
            self.save_StationsConfig()

    def _load_StationsConfig(self, path: str | Path) -> TB_StationsConfig:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return from_dict(
            data_class=TB_StationsConfig,
            data=data,
            config=Config(
                type_hooks={
                    TB_StationType: TB_StationType,
                },
                check_types=True,
                strict=False,
            ),
        )

    def apply_station_config(self, stationConfig: TB_StationsConfig):
        self._validateStationConfig(stationConfig)
        self._stationsConfig = stationConfig
        self.save_StationsConfig()

    def save_StationsConfig(self):
        self._save_StationsConfig(self._stationsConfig, self._stationsFile)

    def _save_StationsConfig(self, stationConfig: TB_StationsConfig, path: str | Path):
        with open(path, "w", encoding="utf-8") as configFile:
            json.dump(asdict(stationConfig), configFile, indent=2)

    def _validateStationConfig(self, stations: TB_StationsConfig) -> bool:
        """validate the current station configuration"""
        self._logger.info("Validate station config.")

        # check if a unique id not given, set then the unique id and save the config
        @dataclass
        class UserData:
            hasChanged: bool

        self._stationFlatList.clear()

        def entryCallback(entry: TB_StationEntry, userData: object):

            if entry.uniqueId == "":
                entry.uniqueId = str(uuid.uuid4())
                cast(UserData, userData).hasChanged = True
            if entry.type == TB_StationType.FOLDER and entry.caption is None:
                raise TB_Exception("Folder need a caption!")
            if entry.type == TB_StationType.PLAYLIST and (entry.caption is None or entry.path is None):
                raise TB_Exception("A playlist entry need a caption and a path to the m3u playlist!")
            if entry.type == TB_StationType.WEBRADIO and (entry.caption is None or entry.url is None):
                raise TB_Exception("A webradio entry need a caption and a url!")
            self._stationFlatList[entry.uniqueId] = entry

        userdata = UserData(hasChanged=False)
        self.traverseStations(stations, lambda entry, data: entryCallback(entry, data), userdata)
        return userdata.hasChanged

    def traverseStations(
        self,
        stations: TB_StationsConfig,
        callback: Callable[[TB_StationEntry, object], None],
        userData: object = None,
    ):
        self._traverseStations(stations.stations, callback, userData)

    def _traverseStations(
        self,
        stations: list[TB_StationEntry],
        callback: Callable[[TB_StationEntry, object], None],
        userData: object,
    ):

        for station in stations:
            callback(station, userData)
            if station.items is not None:
                self._traverseStations(station.items, callback, userData)

    def get_station_by_id(self, id: str) -> TB_StationEntry | None:
        return self._stationFlatList.get(id, None)

    def get_next_station(self, currentId: str | None, type: TB_StationType) -> TB_StationEntry | None:
        stations = list(self._stationFlatList.values())
        index = next((i for i, station in enumerate(stations) if station.uniqueId == currentId), None)
        if index is None:
            return None

        # search after the current
        nextStation = next(
            (station for station in stations[index + 1 :] if station.type == type),
            None,
        )
        if nextStation is None:
            # search from begin
            nextStation = next(
                (station for station in stations if station.type == type),
                None,
            )

        return nextStation

    def get_previous_station(self, currentId: str | None, type: TB_StationType) -> TB_StationEntry | None:
        stations = list(self._stationFlatList.values())
        index = next((i for i, station in enumerate(stations) if station.uniqueId == currentId), None)
        if index is None:
            return None

        # Search before the current
        previousStation = next((station for station in reversed(stations[:index]) if station.type == type), None)
        if previousStation is None:
            # Search from end
            previousStation = next((station for station in reversed(stations) if station.type == type), None)

        return previousStation


INIT_STATIONS = TB_StationsConfig(
    stations=[
        TB_StationEntry(
            type=TB_StationType.WEBRADIO,
            caption="BigFm",
            url="https://stream.bigfm.de/deutschland/mp3-128/stream.bigfm.de",
        ),
        TB_StationEntry(type=TB_StationType.SEPARATOR),
        TB_StationEntry(
            type=TB_StationType.WEBRADIO,
            caption="Antenne 1",
            url="http://stream.antenne1.de/a1stg/livestream2.mp3",
        ),
        TB_StationEntry(
            type=TB_StationType.FOLDER,
            caption="Playlists",
            items=[
                TB_StationEntry(
                    type=TB_StationType.PLAYLIST,
                    caption="Sample Playlist",
                    volumeDelta=3,
                    path="${HOME}/music/playlist/06_Top.m3u",
                )
            ],
        ),
    ]
)
