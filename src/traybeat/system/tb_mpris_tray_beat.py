from copy import deepcopy

from traybeat.lib.tb_const import APP_ID, APP_NAME, DESKTOP_ENTRY_NAME
from traybeat.lib.tb_i_core import PlayerChangedData, TB_CorePlayerInfo, TB_CorePlayerMeta, TB_I_Core
from traybeat.lib.tb_player import TB_PlayerStatus
from traybeat.system.tb_mpris_player import TB_MPRISPlayer


class TB_MprisTrayBeat:
    def __init__(self, core: TB_I_Core) -> None:

        self._current_cover: str = ""
        self._core = core
        self._mpris = TB_MPRISPlayer(
            app_id=APP_ID,
            identity=APP_NAME,
            desktop_entry=DESKTOP_ENTRY_NAME,
            on_pause=lambda: self._core.player_toogle_pause(),
            on_play=lambda: self._core.player_play(),
            on_next=lambda: self._core.player_next(),
            on_previous=lambda: self._core.player_previous(),
            on_stop=lambda: self._core.player_stop(),
            on_volume_changed=lambda volume: self._core.player_set_volume(int(volume * 100)),  # type: ignore
        )
        self._lastMeta = TB_CorePlayerMeta()
        self._lastState = TB_CorePlayerInfo()

    def _update_mipris_meta(self, meta: TB_CorePlayerMeta):

        track_number = 0
        if self._lastState.isPlayList:
            track_number = self._lastState.playlist_index
        self._mpris.update_metadata(title=meta.title, artist=meta.artist, art_url=meta.cover_file, url=meta.cover_file, track_number=track_number)

    def _update_mipris_state(self, info: TB_CorePlayerInfo):

        self._mpris.update_volume(info.volume)

        match info.state:
            case TB_PlayerStatus.PAUSED:
                self._mpris.update_status("Paused")
            case TB_PlayerStatus.PLAYING:
                self._mpris.update_status("Playing")
            case TB_PlayerStatus.STOPPED:
                self._mpris.update_status("Stopped")
            case _:
                pass

    def _on_player_changed(self, data: PlayerChangedData):
        if data.meta is not None:
            self._lastMeta = deepcopy(data.meta)
        if data.player_info is not None:
            self._lastState = deepcopy(data.player_info)

        self._update_mipris_meta(self._lastMeta)
        self._update_mipris_state(self._lastState)

    async def start(self):
        self._core.player_changed_subscribe(lambda data: self._on_player_changed(data))
        await self._mpris.start()

    async def stop(self):
        self._core.player_changed_unsubscribe(lambda data: self._on_player_changed(data))
        await self._mpris.stop()
