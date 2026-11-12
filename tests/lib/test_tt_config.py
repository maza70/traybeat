# pyright: reportPrivateUsage=false
import copy
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from traybeat.core.tb_config import (
    INIT_STATIONS,
    TB_Config,
    TB_EntryType,
    TB_StationEntry,
)
from traybeat.lib.tb_exception import TB_Exception


def test_StationConfig():
    filepath = Path(__file__).resolve().parent
    tempDir = Path(filepath, "../files/temp/stationConfig")
    shutil.rmtree(tempDir, ignore_errors=True)
    tempDir.mkdir(parents=True, exist_ok=True)
    subject = TB_Config()
    stationsConfig = copy.deepcopy(INIT_STATIONS)

    @dataclass
    class IntRef:
        value: int

    def entryCallback(entry: TB_StationEntry, userdata: object) -> None:
        if entry.uniqueId == "":
            entry.uniqueId = "parsed"
            cast(IntRef, userdata).value += 1

    count = IntRef(value=0)
    subject._traverseStations(
        stationsConfig.stations,
        lambda entry, data: entryCallback(entry, data),
        userData=count,
    )

    assert count.value == 5
    assert stationsConfig.stations[0].uniqueId == "parsed"
    assert stationsConfig.stations[3].items is not None
    assert stationsConfig.stations[3].items[0].uniqueId == "parsed"

    subject._save_StationsConfig(stationsConfig, Path(tempDir, "stations.json"))
    # test if load works
    stationsConfig = subject._load_StationsConfig(Path(tempDir, "stations.json"))
    assert stationsConfig.stations[0].uniqueId == "parsed"


def test_validateError():
    subject = TB_Config()
    stationsConfig = copy.deepcopy(INIT_STATIONS)
    subject._validateStationConfig(stationsConfig)

    with pytest.raises(TB_Exception):
        stationsConfig = copy.deepcopy(INIT_STATIONS)
        stationsConfig.stations[0].url = None
        subject._validateStationConfig(stationsConfig)
    with pytest.raises(TB_Exception):
        stationsConfig = copy.deepcopy(INIT_STATIONS)
        stationsConfig.stations[3].caption = None
        subject._validateStationConfig(stationsConfig)
    with pytest.raises(TB_Exception):
        stationsConfig = copy.deepcopy(INIT_STATIONS)
        assert stationsConfig.stations[3].items is not None
        stationsConfig.stations[3].items[0].path = None
        subject._validateStationConfig(stationsConfig)


def test_nextStation():
    subject = TB_Config()
    stationsConfig = copy.deepcopy(INIT_STATIONS)
    subject._validateStationConfig(stationsConfig)
    next_station = subject.get_next_station("1234", TB_EntryType.WEBRADIO)
    assert next_station is None

    next_station = subject.get_next_station(stationsConfig.stations[2].uniqueId, TB_EntryType.WEBRADIO)  # type: ignore
    assert next_station is not None
    assert next_station.uniqueId == stationsConfig.stations[0].uniqueId

    next_station = subject.get_next_station(stationsConfig.stations[0].uniqueId, TB_EntryType.WEBRADIO)  # type: ignore
    assert next_station is not None
    assert next_station.uniqueId == stationsConfig.stations[2].uniqueId

    next_station = subject.get_next_station(stationsConfig.stations[0].uniqueId, TB_EntryType.PLAYLIST)  # type: ignore
    assert next_station is not None
    assert stationsConfig.stations[3].items is not None
    assert next_station.uniqueId == stationsConfig.stations[3].items[0].uniqueId

    # test if no station with the type in list
    stationsConfig.stations.remove(stationsConfig.stations[3])  # remove playlistfolder no playlists in stations
    next_station = subject.get_next_station("12", TB_EntryType.PLAYLIST)
    assert next_station is None


def test_prevStation():
    subject = TB_Config()
    stationsConfig = copy.deepcopy(INIT_STATIONS)
    subject._validateStationConfig(stationsConfig)
    prev_station = subject.get_previous_station("1234", TB_EntryType.WEBRADIO)
    assert prev_station is None

    prev_station = subject.get_previous_station(stationsConfig.stations[2].uniqueId, TB_EntryType.WEBRADIO)  # type: ignore
    assert prev_station is not None
    assert prev_station.uniqueId == stationsConfig.stations[0].uniqueId

    prev_station = subject.get_previous_station(stationsConfig.stations[0].uniqueId, TB_EntryType.WEBRADIO)  # type: ignore
    assert prev_station is not None
    assert prev_station.uniqueId == stationsConfig.stations[2].uniqueId

    prev_station = subject.get_previous_station(stationsConfig.stations[0].uniqueId, TB_EntryType.PLAYLIST)  # type: ignore
    assert prev_station is not None
    assert prev_station.uniqueId == stationsConfig.stations[3].items[0].uniqueId  # type: ignore

    # test if no station with the type in list
    stationsConfig.stations.remove(stationsConfig.stations[3])  # remove playlistfolder no playlists in stations
    prev_station = subject.get_previous_station("12", TB_EntryType.PLAYLIST)
    assert prev_station is None
