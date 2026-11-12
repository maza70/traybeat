import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gio", "2.0")


import logging
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from typing import Any

import setproctitle
from dacite import Config, from_dict
from gi.repository import (
    Gio,  # type: ignore
    GLib,  # type: ignore
)

from traybeat.core.tb_config import (
    TB_Config,
    TB_EntryType,
    TB_StartupConfig,
    TB_StationEntry,
    TB_StationsConfig,
)
from traybeat.core.tb_http_server import TB_HttpAction, TB_HttpServer
from traybeat.core.tb_meta_collector import TB_MetaCollector
from traybeat.core.tb_state import TB_State
from traybeat.core.tb_websocket import TB_WebSocket, TB_WsAction
from traybeat.gui.tb_icons import TB_Icons
from traybeat.gui.tray_icon import TrayIcon
from traybeat.lib.tb_const import APP_ID, APP_NAME, APP_VERSION, TEMP_PATH
from traybeat.lib.tb_dispatch import TB_Dispatch
from traybeat.lib.tb_exception import TB_Exception
from traybeat.lib.tb_i_core import (
    OnCorePlayerChanged,
    PlayerChangedData,
    TB_CorePlayerInfo,
    TB_CorePlayerMeta,
    TB_CorePlayerState,
    TB_I_Core,
)
from traybeat.lib.tb_player import (
    TB_Player,
    TB_PlayerStatus,
)
from traybeat.lib.tb_util import TB_Util
from traybeat.system.tb_mpris_tray_beat import TB_MprisTrayBeat
from traybeat.system.tb_shutdown_watchdog import TB_ShutdownWatchdog
from traybeat.system.tb_standby_monitor import TB_StandbyMonitor
from traybeat.system.tb_traybeat_dbus_player_interface import TB_TrayBeatDBusPlayerInterface


class Core(TB_I_Core):
    _logger = logging.getLogger(__name__)

    def __init__(self, startupConfig: TB_StartupConfig):
        logging.getLogger("PIL").setLevel(logging.WARNING)
        self._player_change_listeners: list[OnCorePlayerChanged] = []
        self._currentStation: TB_StationEntry | None = None

        self._dispatcher = TB_Dispatch()
        self._startupConfig = startupConfig
        if self._startupConfig.logFile:
            handler = logging.FileHandler(self._startupConfig.logFile, encoding="utf-8")
        else:
            handler = logging.StreamHandler(sys.stderr)

        loglevel = logging.getLevelNamesMapping().get(startupConfig.traceLevel.upper())
        if loglevel is None:
            raise TB_Exception("TraceLevel in configuration is unknown")
        logging.basicConfig(
            level=loglevel,
            format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[handler],
        )

        self._gio_application = Gio.Application(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        if not self._gio_application.register(None):
            self._logger.info(f"can't register {APP_NAME}, did you start twice")
            raise SystemExit(1)

        self._logger.info(f"Temp directory is: {TEMP_PATH}")
        self._logger.info(f"App-Version is: {APP_VERSION}")
        self._logger.debug("initialize configuration")
        self._config = TB_Config()
        self._config.initialize()
        self._config.load_StationsConfig()

        setproctitle.setproctitle(APP_NAME)

        self._logger.debug("initialize trayicon")
        self._icons = TB_Icons(startupConfig.icon_theme)
        self._tray_icon = TrayIcon(self, self._icons, self._dispatcher)
        self._logger.debug("initialize player")
        self._meta_collector = TB_MetaCollector(on_meta_change=lambda collector: self._collector_on_meta(collector), collectTimeout=0.2)
        self._gplayer = TB_Player(
            on_metadata=lambda metadata: self._gplayer_on_meta(metadata),
            # on_cover=lambda mimetype,image_data: self._gplayer_on_cover(mimetype,image_data),
            on_status_changed=lambda oldStatus, newStatus: self._gplayer_on_status_changed(oldStatus, newStatus),
            use_glib_mainloop=False,
        )
        self._shutdown_watchdog = TB_ShutdownWatchdog(on_shutdown=self._system_shutdown)

        self._mpris = TB_MprisTrayBeat(self)
        self._dbusPlayerService = TB_TrayBeatDBusPlayerInterface(self, self._dispatcher)
        self._websocket = TB_WebSocket(
            self,
            self._dispatcher,
            on_action=lambda socket, action: self._on_websocket_action(socket, action),
            host=startupConfig.websocket_bind,
            port=startupConfig.websocket_port,
        )
        self._httpServer = TB_HttpServer(
            asdict(self._config.StationsConfig),
            host=startupConfig.webserver_bind,
            port=startupConfig.webserver_port,
            on_action=lambda httpServer, action: self._on_http_action(httpServer, action),
        )
        self._standby_monitor = TB_StandbyMonitor(
            core=self,
            on_sleep=lambda: self._system_standby(),
            on_wakeup=lambda state, player_state: self._system_resume(state, player_state),
        )
        self._standby_monitor.start()
        self._tray_icon.about_url = self._httpServer.about_url
        self._tray_icon.station_editor_url = self._httpServer.station_url
        self._tray_icon.player_controls_url = self._httpServer.player_controls_url

    # -------------------------------------------------------------------
    # Methods for control the player
    # -------------------------------------------------------------------
    # region music Player methods

    def _collector_on_meta(self, collector: TB_MetaCollector) -> None:
        self.player_notify_data_changed(PlayerChangedData(meta=self.player_meta()))

    def _gplayer_on_meta(self, metadata: Any) -> None:
        self._meta_collector.update(metadata)
        # self._update_gui()

    def _gplayer_on_status_changed(self, oldStatus: TB_PlayerStatus, newStatus: TB_PlayerStatus) -> None:

        self._logger.debug(f"player status changed from {oldStatus} -> {newStatus}")
        match newStatus:
            case TB_PlayerStatus.CONNECTING:
                if self._currentStation:
                    self._meta_collector.new_song(self._currentStation)
                self._logger.debug("Connecting")
            case TB_PlayerStatus.PLAYING | TB_PlayerStatus.STOPPED | TB_PlayerStatus.PAUSED | TB_PlayerStatus.ERROR:
                self.player_notify_data_changed(PlayerChangedData(player_info=self.player_info()))
            case _:
                pass

    def _gplayer_pause_toogle(self) -> None:
        if self._gplayer.status == TB_PlayerStatus.PLAYING:
            self._save_state()
            self._gplayer.pause()
        if self._gplayer.status == TB_PlayerStatus.PAUSED:
            self._gplayer_play_current()

    def _gplayer_play_current(self) -> None:
        if self._currentStation is not None:
            status = self._gplayer.get_status()
            if status.gst_state == "null":
                # we are started without autoplay check exit status and then play the last station
                self._gplayer_play(self._currentStation)
            else:
                self._logger.info("Resume playing")
                self._gplayer.play()

    def _gplayer_play(self, station: TB_StationEntry):

        if self._currentStation is not None:
            state = TB_State()
            state.update_station_state(self._currentStation, self._gplayer.get_status())
            state.save()

        self._gplayer.volume_delta = station.volumeDelta / 100
        self._currentStation = station

        if station.type == TB_EntryType.WEBRADIO:
            self._logger.info(f"play:{station.caption} volume adjust:{station.volumeDelta}% filename:{station.url}")
            self._gplayer.play_url(station.url)  # type: ignore

        elif station.type == TB_EntryType.PLAYLIST:
            self._logger.info(f"play:{station.caption} volume adjust:{station.volumeDelta}% filename:{station.path}")
            state = TB_State()
            stationState = state.get_station_state(station.uniqueId)
            self._gplayer.load_playlist(
                filename=station.path,  # type: ignore
                autoplay=True,
                startindex=stationState.playlist_index,
                startposition=stationState.playlist_song_pos,
            )  # type: ignore
        else:
            self._logger.error("Station type unknown")

    def _gplayer_stop(self) -> None:
        self._logger.info("Stop player")
        self._save_state()
        self._gplayer.stop()

    # endregion
    # -------------------------------------------------------------------
    # Implement the TT_I_Core interface
    # -------------------------------------------------------------------
    # region TT_I_Core interface

    @property
    def current_station(self) -> TB_StationEntry | None:
        return self._currentStation

    def quit(self) -> None:
        """Save quit TrayBeat"""
        self._logger.info(f"Quit {APP_NAME}")
        self._save_state()
        self._standby_monitor.stop()
        self._httpServer.stop()
        self._gplayer.close()
        self._mainloop.quit()

    def player_play(self) -> None:
        """Start playback."""
        self._gplayer_play_current()

    def player_play_station(self, station_id: str) -> None:
        station = self._config.get_station_by_id(station_id)
        if station is not None:
            self.player_stop()
            self._gplayer_play(station)

    def player_toogle_pause(self) -> None:
        """Pause playback."""
        self._gplayer_pause_toogle()

    def player_stop(self) -> None:
        """stop playback."""
        self._gplayer_stop()

    def player_previous(self) -> None:
        playerStatus = self._gplayer.get_status()
        if playerStatus.status == TB_PlayerStatus.STOPPED:
            self._logger.warning("play previous not possible, player is in stopped state")
            return
        if self._currentStation is None:
            self._logger.warning("play previous not possible, no curent station")
            return
        if self._currentStation.type == TB_EntryType.PLAYLIST:
            self._logger.info("play previous song in playlist")
            self._gplayer.previous()
        else:
            prev_station = self._config.get_previous_station(self._currentStation.uniqueId, TB_EntryType.WEBRADIO)
            if prev_station is not None:
                self._logger.info("play previous webradio station.")
                self._gplayer_play(prev_station)
            else:
                self._logger.warning("Previous Webradio station not found!")

    def player_next(self) -> None:
        playerStatus = self._gplayer.get_status()
        if playerStatus.status == TB_PlayerStatus.STOPPED:
            self._logger.warning("play next not possible, player is in stopped state")
            return
        if self._currentStation is None:
            self._logger.warning("play next not possible, no curent station")
            return
        if self._currentStation.type == TB_EntryType.PLAYLIST:
            self._logger.info("play next song in playlist")
            self._gplayer.next()
        else:
            nextStation = self._config.get_next_station(self._currentStation.uniqueId, TB_EntryType.WEBRADIO)
            if nextStation is not None:
                self._logger.info("play next webradio station.")
                self._gplayer_play(nextStation)
            else:
                self._logger.warning("Next Webradio station not found!")

    def player_set_volume(self, volume: int) -> None:
        self._gplayer.volume = float(volume / 100.0)
        self.player_notify_data_changed(PlayerChangedData(player_info=self.player_info()))

    def player_volume_step(self, delta: int) -> None:
        """increment or decrement the volume"""
        currentVolume = self.player_get_volume()
        currentVolume = currentVolume + delta
        currentVolume = min(currentVolume, 100)
        currentVolume = max(currentVolume, 0)
        self.player_set_volume(currentVolume)

    def player_get_volume(self) -> int:
        return int(self._gplayer.volume * 100)

    def player_stations(self) -> TB_StationsConfig:
        return deepcopy(self._config.StationsConfig)

    def player_info(self) -> TB_CorePlayerInfo:
        status = self._gplayer.get_status()
        result = TB_CorePlayerInfo(
            station=self._currentStation,
            volume=int(status.volume * 100),
            volume_gain=int(status.volume_delta * 100),
            playlist_index=status.playlist_index,
            playlist_length=status.playlist_length,
            playlist_song_position=status.playlist_song_position,
        )
        match status.status:
            case TB_PlayerStatus.PLAYING:
                result.state = TB_CorePlayerState.PLAYING
            case TB_PlayerStatus.STOPPED:
                result.state = TB_CorePlayerState.STOPPED
            case TB_PlayerStatus.PAUSED:
                result.state = TB_CorePlayerState.PAUSED
            case TB_PlayerStatus.ERROR:
                result.state = TB_CorePlayerState.ERROR
                result.error = self._gplayer.last_error
            case _:
                result.state = TB_CorePlayerState.UNKNOWN

        return result

    def player_meta(self) -> TB_CorePlayerMeta:
        meta = self._meta_collector.current_meta
        return TB_CorePlayerMeta(artist=meta.artist, title=meta.title, cover_file=meta.cover_file, cover_mimetype=meta.cover_mimetype)

    def player_changed_subscribe(self, onchanged: OnCorePlayerChanged):
        """subscript to notify when state or meta is changed"""
        if onchanged not in self._player_change_listeners:
            self._player_change_listeners.append(onchanged)

    def player_changed_unsubscribe(self, onchanged: OnCorePlayerChanged):
        """unsubscribe from notification"""
        if onchanged in self._player_change_listeners:
            self._player_change_listeners.remove(onchanged)

    def player_notify_data_changed(self, data: PlayerChangedData):
        """notify changed"""
        for callback in self._player_change_listeners:
            callback(data)

    # endregion

    # -------------------------------------------------------------------
    # TrayBeat related methods
    # -------------------------------------------------------------------
    # region TrayBeat methods
    def _system_shutdown(self, reason: str) -> None:
        """callback for the shutdown_watchdog to clean shutdown TrayBeat

        Args:
            reason (str): shutdown Reason
        """
        self._logger.info(f"Event for shutdown received: {reason}")
        self.quit()

    def _system_standby(self):
        self._logger.debug("system go to standy")
        self.player_stop()

    def _system_resume(self, state: Any, wakeup_player_state: TB_CorePlayerState):
        if wakeup_player_state == TB_CorePlayerState.PLAYING:
            self.player_play()

    def _edit_stations(self):
        subprocess.Popen(["xdg-open", self._httpServer.station_url])

    def _open_about(self):
        subprocess.Popen(["xdg-open", self._httpServer.about_url])

    def _on_websocket_action(self, socket: TB_WebSocket, action: TB_WsAction):
        if action == TB_WsAction.CLIENT_CONNECT:
            socket.publish(PlayerChangedData(meta=self.player_meta(), player_info=self.player_info()))

    def _on_http_action(
        self,
        server: TB_HttpServer,
        action: TB_HttpAction,
    ):
        match action:
            case TB_HttpAction.STATION_CONFIG_CHANGED:
                stationConfig = from_dict(
                    data_class=TB_StationsConfig,
                    data=server.config,
                    config=Config(
                        type_hooks={
                            TB_EntryType: TB_EntryType,
                        },
                        check_types=True,
                        strict=False,
                    ),
                )
                self._config.apply_station_config(stationConfig)
                self._tray_icon.updateStations(self._config.StationsConfig)
            case TB_HttpAction.PLAYER_PLAY:
                self.player_play()
            case TB_HttpAction.PLAYER_STOP:
                self.player_stop()
            case TB_HttpAction.PLAYER_PAUSE:
                self.player_toogle_pause()
            case TB_HttpAction.PLAYER_NEXT:
                self.player_next()
            case TB_HttpAction.PLAYER_PREVIOUS:
                self.player_previous()
            case TB_HttpAction.PLAYER_VOLUME_UP:
                self.player_volume_step(+5)
            case TB_HttpAction.PLAYER_VOLUME_DOWN:
                self.player_volume_step(-5)
            case _:
                pass

    def _on_initialized(self) -> bool:
        """initialize the TrayBeat gui called by GLIB

        Returns:
            bool: return to GLIB
        """

        self._httpServer.set_template_var("WEBSOCKET_PORT", str(self._websocket.port))
        self._httpServer.set_template_var("WEBSOCKET_HOST", str(self._websocket.host))
        self._httpServer.set_template_var("TRAYBEAT_VERSION", APP_VERSION)

        self._httpServer.start()

        state = TB_State()
        self._gplayer.volume = state.tray_beat_state.playerVolume / 100

        if state.tray_beat_state.lastStationId == "":
            self._logger.info("No station in exit state")
            return GLib.SOURCE_REMOVE

        station = self._config.get_station_by_id(state.tray_beat_state.lastStationId)
        if station is None:
            self._logger.error(f"station with id {state.tray_beat_state.lastStationId} not found")
            return GLib.SOURCE_REMOVE

        if self._startupConfig.play:
            self._gplayer_play(station=station)
        else:
            self._currentStation = station
        return GLib.SOURCE_REMOVE

    def _save_state(self) -> None:
        playerStatus = self._gplayer.get_status()
        state = TB_State()
        if self._currentStation is None:
            state.tray_beat_state.playerVolume = int(playerStatus.volume * 100)
        else:
            state.tray_beat_state.playerVolume = int(playerStatus.volume * 100)
            state.update_station_state(self._currentStation, self._gplayer.get_status())
            state.save()

    def start(self) -> None:
        """Start TrayBeat synchron"""
        self._logger.info(f"Start {APP_NAME}")
        self._mainloop = GLib.MainLoop()

        try:
            self._dispatcher.start()
            self._dispatcher.fnc(self._mpris.start()).result()
            self._dispatcher.fnc(self._websocket.start()).result()
            self._dispatcher.fnc(self._tray_icon.start(self._config.StationsConfig)).result()
            self._dispatcher.fnc(self._shutdown_watchdog.start()).result()
            self._dispatcher.fnc(self._dbusPlayerService.register()).result()
            self._shutdown_watchdog.attach_glib_signals(self._mainloop.quit)
            GLib.idle_add(self._on_initialized)
            # blocking,.  till  quit()
            self._mainloop.run()

        finally:
            # Tray stop clean
            self._dbusPlayerService.unregister()
            self._dispatcher.fnc(self._websocket.stop()).result()
            self._dispatcher.fnc(self._tray_icon.stop()).result()
            self._dispatcher.fnc(self._mpris.stop()).result()

            self._dispatcher.stop()
            TB_Util.del_directory_content(TEMP_PATH)


# endregion
