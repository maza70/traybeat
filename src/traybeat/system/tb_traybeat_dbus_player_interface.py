# pyright: reportUnknownArgumentType=false
import json
import logging
from dataclasses import asdict

from dbus_next.aio.message_bus import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from traybeat.lib.tb_const import APP_DBUS_PATH, APP_DBUS_PLAYER_SERVICE
from traybeat.lib.tb_dispatch import TB_Dispatch
from traybeat.lib.tb_i_core import PlayerChangedData, TB_I_Core


class TB_TrayBeatDBusPlayerInterface(ServiceInterface):
    """DBUS Interface to controll traybeat over dbus"""

    _logger = logging.getLogger(__name__)

    def __init__(self, core: TB_I_Core, disp: TB_Dispatch):
        super().__init__(APP_DBUS_PLAYER_SERVICE)  # name of the interface de.maza.traybeat.player
        self._core = core
        self._dispacher = disp
        self._bus: MessageBus | None = None

    @method()
    def Play(self):  # type: ignore
        """Play the current station"""
        self._logger.info("Play invoke")
        self._core.player_play()

    @method()
    def PlayStation(self, stationId: "s"):  # type: ignore
        """Play the station with the id"""
        self._logger.info("Play invoke")
        self._core.player_play()

    @method()
    def Stop(self):
        self._logger.info("Stop invoke")
        self._core.player_stop()

    @method()
    def PauseToogle(self):
        self._logger.info("Pause_toogle invoke")
        self._core.player_toogle_pause()

    @method()
    def SetVolume(self, volume: "i"):  # type: ignore
        self._logger.info("SetVolume invoke")
        volume = max(volume, 0)
        volume = min(volume, 100)
        self._core.player_set_volume(volume)

    @method()
    def Next(self):  # type: ignore
        self._logger.info("Next invoke")
        self._core.player_next()

    @method()
    def Previous(self):  # type: ignore
        self._logger.info("Previous invoke")
        self._core.player_previous()

    @method()
    def GetStateAsJson(self) -> "s":  # type: ignore
        self._logger.info("getStateAsJson invoke")
        state = self._core.player_info()
        return json.dumps(asdict(state), ensure_ascii=False, indent=2)

    @method()
    def GetStationsAsJson(self) -> "s":  # type: ignore
        self._logger.info("getStationsAsJson invoke")
        stations = self._core.player_stations()
        return json.dumps(asdict(stations), ensure_ascii=False, indent=2)

    @signal()
    def PlayerChanged(self, what: "s") -> "s":  # type: ignore
        """called when metadata or state of the player changed

        Args:
            what (s): META|STATE


        """
        return what  # type: ignore

    def Broadcast(self, data: PlayerChangedData):
        if data.meta is not None:
            self.PlayerChanged("META")  # type: ignore
        if data.player_info is not None:
            self.PlayerChanged("STATE")  # type: ignore

    async def register(self):

        self._bus = await MessageBus().connect()
        self._bus.export(APP_DBUS_PATH, self)  # /de/maza/traybeat
        await self._bus.request_name(APP_DBUS_PLAYER_SERVICE)  # de.maza.traybeat.player
        self._core.player_changed_subscribe(lambda data: self.Broadcast(data))

    def unregister(self):
        if self._bus is not None:
            self._core.player_changed_unsubscribe(lambda data: self.Broadcast(data))
            self._bus.unexport(APP_DBUS_PATH, self)
            self._bus.disconnect()
