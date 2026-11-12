import asyncio
import logging
import subprocess
from copy import deepcopy

from traybeat.core.tb_config import TB_EntryType, TB_StationEntry, TB_StationsConfig
from traybeat.gui.tb_icons import TB_Icons, TB_IconsName
from traybeat.gui.tb_resource import TB_Resource
from traybeat.gui.tb_tray_menu import TB_MenuItem, TB_TrayMenu
from traybeat.lib.tb_const import APP_ID, APP_NAME
from traybeat.lib.tb_dispatch import TB_Dispatch
from traybeat.lib.tb_i_core import (
    PlayerChangedData,
    TB_CorePlayerInfo,
    TB_CorePlayerMeta,
    TB_CorePlayerState,
    TB_I_Core,
)
from traybeat.lib.tb_util import TB_Util

from .tb_tray_icon import TB_TrayIcon


class TrayIcon:
    _logger = logging.getLogger(__name__)

    def __init__(
        self,
        core: TB_I_Core,
        icons: TB_Icons,
        disp: TB_Dispatch,
    ) -> None:

        self._loop: asyncio.AbstractEventLoop | None = None
        self._metaEntry: TB_MenuItem | None
        self._station_editor_url: str = ""
        self._about_url: str = ""
        self._player_controls_url: str = ""
        self._lastPlayerState: TB_CorePlayerInfo | None = None
        self._lastMeta: TB_CorePlayerMeta | None = None

        self._icons = icons
        self._core = core
        self._disp = disp

        self._tray_icon = TB_TrayIcon(APP_ID, APP_NAME)
        self._tray_icon.on_activate = lambda x, y: self._onActivate(x, y)
        self._tray_icon.on_secondary_activate = lambda x, y: self._onSecondaryActivate(x, y)
        self._tray_icon.on_scroll = lambda delta, orientation: self._on_scroll(delta, orientation)
        self._tray_icon.set_icon(icons.GetIcon(TB_IconsName.TRAY_STOP))
        self._tray_icon.set_tooltip(title="TrayBeat", description="")

        svg_icons = TB_Resource.get_folder("svg")

        self._tray_icon.set_icon_theme_path(str(svg_icons))

    def _onActivate(self, x: int, y: int):
        self._core.player_next()

    def _onSecondaryActivate(self, x: int, y: int):
        state = self._core.player_info()
        if state.state in [TB_CorePlayerState.PAUSED, TB_CorePlayerState.STOPPED]:
            self._core.player_play()
        else:
            self._core.player_stop()

    def _on_scroll(self, delta: int, orientation: str) -> None:
        if orientation == "Vertical":
            if delta > 0:
                delta = 5
            else:
                delta = -5
            self._core.player_volume_step(delta)

    def _on_station_clicked(self, item: TB_MenuItem):
        if isinstance(item.user_data, TB_StationEntry):
            self._core.player_play_station(item.user_data.uniqueId)

    def _on_play_clicked(self, item: TB_MenuItem):
        self._core.player_play()

    def _on_pause_clicked(self, item: TB_MenuItem):
        self._core.player_toogle_pause()

    def _on_stop_clicked(self, item: TB_MenuItem):
        self._core.player_stop()

    def _on_edit_stations_clicked(self, item: TB_MenuItem):
        subprocess.Popen(["xdg-open", self._station_editor_url])

    def _on_player_controls_clicked(self, item: TB_MenuItem):
        subprocess.Popen(["xdg-open", self._player_controls_url])

    def _on_about_clicked(self, item: TB_MenuItem):
        subprocess.Popen(["xdg-open", self._about_url])

    def _on_quit_clicked(self, item: TB_MenuItem):
        self._core.quit()

    def _on_player_changed(self, data: PlayerChangedData):
        if data.meta is not None:
            self._lastMeta = deepcopy(data.meta)
            self._meta_item_update(self._lastMeta)
        if data.player_info is not None:
            self._lastPlayerState = deepcopy(data.player_info)
            self._icon_update(self._lastPlayerState)

        self._tooltipp_update(self._lastMeta, self._lastPlayerState)

    def _tooltipp_update(self, meta: TB_CorePlayerMeta | None, playerState: TB_CorePlayerInfo | None):
        stationInfo = ""
        if playerState is not None and playerState.state == TB_CorePlayerState.ERROR:
            self._tray_icon.set_tooltip(title="TrayBeat Error", description=playerState.error)
            return

        if self._core.current_station is not None and playerState is not None:
            if self._core.current_station.type == TB_EntryType.PLAYLIST:
                stationInfo = f"Playlist:{self._core.current_station.caption} [{playerState.playlist_index + 1}/{playerState.playlist_length}]\n"
            else:
                stationInfo = f"Webradio: {self._core.current_station.caption}\n"
            self._tray_icon.set_tooltip(title="TrayBeat", description=stationInfo)
            if meta is not None:
                if meta.title != "":
                    stationInfo += f"{meta.title}\n"
                if meta.artist != "":
                    stationInfo += f"{meta.artist}\n"

            stationInfo += "\n" + f"Volume  :{playerState.volume}%\n" + f"Gain    :{playerState.volume_gain}\n" + f"Status  :{playerState.state}\n"
        self._tray_icon.set_tooltip(title="TrayBeat", description=stationInfo)

    def _meta_item_update(self, meta: TB_CorePlayerMeta):
        if self._metaEntry is not None:
            if self._core.current_station is not None:
                text = f"-= {self._core.current_station.caption} =-"
                if meta.artist:
                    text += "\n" + TB_Util.trim(meta.artist, 30)
                if meta.title:
                    text += "\n" + TB_Util.trim(meta.title, 30)
            else:
                text = "-= no station =-"
            self._metaEntry.label = text

    def _icon_update(self, playerState: TB_CorePlayerInfo):
        match playerState.state:
            case TB_CorePlayerState.ERROR:
                self._tray_icon.set_icon(self._icons.GetIcon(TB_IconsName.TRAY_ERROR))
            case TB_CorePlayerState.PLAYING:
                self._tray_icon.set_icon(self._icons.GetIcon(TB_IconsName.TRAY_PLAY))
            case TB_CorePlayerState.STOPPED:
                self._tray_icon.set_icon(self._icons.GetIcon(TB_IconsName.TRAY_STOP))
            case TB_CorePlayerState.PAUSED:
                self._tray_icon.set_icon(self._icons.GetIcon(TB_IconsName.TRAY_PAUSE))
            case TB_CorePlayerState.ERROR:  # pyright: ignore[reportUnnecessaryComparison]
                self._tray_icon.set_icon(self._icons.GetIcon(TB_IconsName.TRAY_ERROR))
            case TB_CorePlayerState.UNKNOWN:
                pass
            case _:
                pass

    def _make_menu(self, stations: TB_StationsConfig, menu: TB_TrayMenu):
        menu.clear()
        self._metaEntry = TB_MenuItem("- not playing -", enabled=False)
        menu.append(self._metaEntry)
        menu.append(TB_MenuItem(separator=True))

        def traverse(entries: list[TB_StationEntry] | None, parentItem: TB_MenuItem | None) -> None:
            if not entries:
                return
            newItem: TB_MenuItem | None = None
            for entry in entries:
                match entry.type:
                    case TB_EntryType.WEBRADIO:
                        newItem = TB_MenuItem(
                            label=entry.caption or "",
                            icon=self._icons.GetIcon(TB_IconsName.WEBRADIO),
                            callback=lambda menuitem: self._on_station_clicked(menuitem),
                            user_data=entry,
                        )

                    case TB_EntryType.PLAYLIST:
                        newItem = TB_MenuItem(
                            label=entry.caption or "",
                            icon=self._icons.GetIcon(TB_IconsName.PLAYLIST),
                            callback=lambda menuitem: self._on_station_clicked(menuitem),
                            user_data=entry,
                        )

                    case TB_EntryType.SEPARATOR:
                        newItem = TB_MenuItem(separator=True)

                    case TB_EntryType.FOLDER:
                        newItem = TB_MenuItem(
                            label=entry.caption or "",
                            icon=self._icons.GetIcon(TB_IconsName.FOLDER),
                            user_data=entry,
                        )
                        traverse(entry.items, newItem)
                    case _:
                        raise TT_Exception("Unknown entry type.")
                if parentItem is not None:
                    parentItem.append(newItem)
                else:
                    menu.append(newItem)  # type: ignore

        traverse(stations.stations, None)
        menu.append(TB_MenuItem(separator=True))
        menu.append(TB_MenuItem(label="Play", icon=self._icons.GetIcon(TB_IconsName.PLAY), callback=lambda item: self._on_play_clicked(item)))
        menu.append(TB_MenuItem(label="Pause", icon=self._icons.GetIcon(TB_IconsName.PAUSE), callback=lambda item: self._on_pause_clicked(item)))
        menu.append(TB_MenuItem(label="Stop", icon=self._icons.GetIcon(TB_IconsName.STOP), callback=lambda item: self._on_stop_clicked(item)))
        menu.append(TB_MenuItem(separator=True))

        traybeat_menu = TB_MenuItem(
            label=APP_NAME, icon=self._icons.GetIcon(TB_IconsName.TRAY_PLAY), callback=lambda item: self._on_stop_clicked(item)
        )
        traybeat_menu.append(
            TB_MenuItem(
                label="Configure stations ...",
                icon=self._icons.GetIcon(TB_IconsName.CONFIG),
                callback=lambda item: self._on_edit_stations_clicked(item),
            )
        )
        traybeat_menu.append(
            TB_MenuItem(
                label="Player gui ...", icon=self._icons.GetIcon(TB_IconsName.MUSIC), callback=lambda item: self._on_player_controls_clicked(item)
            )
        )
        traybeat_menu.append(
            TB_MenuItem(label="About ...", icon=self._icons.GetIcon(TB_IconsName.INFO), callback=lambda item: self._on_about_clicked(item))
        )
        menu.append(traybeat_menu)

        menu.append(TB_MenuItem(label="Quit", icon=self._icons.GetIcon(TB_IconsName.QUIT), callback=lambda item: self._on_quit_clicked(item)))

    @property
    def station_editor_url(self) -> str:
        """the editor url for the stations."""
        return self._station_editor_url

    @station_editor_url.setter
    def station_editor_url(self, value: str) -> None:
        self._station_editor_url = value

    @property
    def about_url(self) -> str:
        """the editor url for the stations."""
        return self._about_url

    @about_url.setter
    def about_url(self, value: str) -> None:
        self._about_url = value

    @property
    def player_controls_url(self) -> str:
        """the editor url for the stations."""
        return self._player_controls_url

    @player_controls_url.setter
    def player_controls_url(self, value: str) -> None:
        self._player_controls_url = value

    def updateStations(self, stations: TB_StationsConfig):
        self._make_menu(stations, self._tray_icon.menu)

    async def start(self, stations: TB_StationsConfig):
        self._loop = asyncio.get_running_loop()
        self._core.player_changed_subscribe(lambda data: self._on_player_changed(data))
        self.updateStations(stations)
        await self._tray_icon.start()

    async def stop(self):
        self._core.player_changed_unsubscribe(lambda data: self._on_player_changed(data))
        await self._tray_icon.stop()
