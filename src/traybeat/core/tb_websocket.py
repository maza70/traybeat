import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum, auto
from pathlib import Path
from typing import Any

from websockets import ServerConnection
from websockets.asyncio.server import serve

from traybeat.core.tb_config import TB_StationEntry
from traybeat.lib.tb_dispatch import TB_Dispatch
from traybeat.lib.tb_i_core import PlayerChangedData, TB_CorePlayerState, TB_I_Core


class TB_WsMessageTyp(StrEnum):
    META = auto()
    PLAYER_INFO = auto()
    ERROR = auto()
    CONNECTED = auto()
    PING = auto()


@dataclass
class TB_WsMessage:
    data_type: TB_WsMessageTyp


@dataclass
class TB_WsMeta(TB_WsMessage):
    title: str = ""
    artist: str = ""
    cover: str = ""


@dataclass
class TB_WsPlayerInfo(TB_WsMessage):
    station: TB_StationEntry | None
    state: TB_CorePlayerState
    error: str = ""
    playlist_index: int = 0
    playlist_length: int = 0
    playlist_song_position: float = 0
    volume: int = 0
    volume_gain: int = 0


@dataclass
class TB_WsData(TB_WsMessage):
    data: dict[str, Any]


class TB_WsAction(StrEnum):
    CLIENT_CONNECT = auto()
    CLIENT_DISCONNECT = auto()


WsActionCallback = Callable[["TB_WebSocket", TB_WsAction], None]


class TB_WebSocket:
    _logger = logging.getLogger(__name__)

    def __init__(
        self,
        core: TB_I_Core,
        disp: TB_Dispatch,
        on_action: WsActionCallback,
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        self._core = core
        self._dispatcher = disp
        self._on_action = on_action
        self._host = host
        self._port = port
        self._server = None
        self._clients = set[ServerConnection]()
        self._lastMeta: TB_WsMeta | None = None
        self._last_player_info: TB_WsPlayerInfo | None = None

    async def _on_player_changed(self, data: PlayerChangedData, broadcast_force: bool = False):

        if data.meta is not None:
            ws_meta = TB_WsMeta(
                data_type=TB_WsMessageTyp.META,
                title=data.meta.title,
                artist=data.meta.artist,
                cover=Path(data.meta.cover_file).name,
            )
            if self._lastMeta != ws_meta or broadcast_force:
                self._lastMeta = ws_meta
                await self.broadcast(asdict(ws_meta))

        if data.player_info is not None:
            ws_player_info = TB_WsPlayerInfo(
                data_type=TB_WsMessageTyp.PLAYER_INFO,
                station=data.player_info.station,
                state=data.player_info.state,
                error=data.player_info.error,
                playlist_index=data.player_info.playlist_index,
                playlist_length=data.player_info.playlist_length,
                playlist_song_position=data.player_info.playlist_song_position,
                volume=data.player_info.volume,
                volume_gain=data.player_info.volume_gain,
            )
            if self._last_player_info != ws_player_info or broadcast_force:
                self._last_player_info = ws_player_info
                await self.broadcast(asdict(ws_player_info))

    @property
    def port(self) -> int:
        return self._port

    @property
    def host(self) -> str:
        return self._host

    def publish(self, data: PlayerChangedData):
        self._dispatcher.sub(self._on_player_changed(data, True))

    async def start(self):
        self._server = await serve(self._handler, self._host, self._port)
        self._port = self._server.sockets[0].getsockname()[1]
        self._logger.info("WebSocket server listening on %s:%s", self._host, self._port)
        self._core.player_changed_subscribe(lambda data: self._dispatcher.sub(self._on_player_changed(data)))

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._core.player_changed_unsubscribe(lambda data: self._dispatcher.sub(self._on_player_changed(data)))

    async def _handler(self, websocket: ServerConnection):
        self._clients.add(websocket)

        try:
            self._on_action(self, TB_WsAction.CLIENT_CONNECT)
            await websocket.send(self._json(TB_WsMessageTyp.CONNECTED, data={"message": "Connected to TrayBeat"}))
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(self._sys_error_json("Invalid JSON"))
            self._on_action(self, TB_WsAction.CLIENT_DISCONNECT)
        except Exception:
            self._logger.exception("WebSocket connection error")

        finally:
            self._clients.discard(websocket)

    def _sys_error_json(self, message: str) -> str:
        return json.dumps(asdict(TB_WsData(data_type=TB_WsMessageTyp.ERROR, data={"message": f"{message}"})))

    def _json(self, type: TB_WsMessageTyp, data: dict[str, Any]) -> str:
        return json.dumps(asdict(TB_WsData(data_type=type, data=data)))

    async def _handle_message(self, websocket: ServerConnection, data: dict[str, Any]):
        command = data.get("command")

        if command == "ping":
            await websocket.send(self._json(type=TB_WsMessageTyp.PING, data={}))

        elif command == "play":
            # TODO: Start playback
            pass

        elif command == "stop":
            # TODO: Stop playback
            pass

        else:
            await websocket.send(self._sys_error_json(f"Unknown command: {command}"))

    async def broadcast(self, data: dict[str, Any]):
        if not self._clients:
            return
        message = json.dumps(data)
        await asyncio.gather(*(client.send(message) for client in self._clients), return_exceptions=True)
