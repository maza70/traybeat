import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum, auto
from pathlib import Path
from typing import Any, cast

from websockets import ConnectionClosed, ServerConnection
from websockets.asyncio.server import Server, serve

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

    # Maximum time a single client may take to accept a message.
    # After that it is considered stuck and is removed so it cannot block the broadcast.
    SEND_TIMEOUT = 1.0

    # An on_action callback taking longer than this (in seconds) is reported in the log.
    SLOW_ACTION_WARN = 0.1

    # Keepalive: detect dead clients (standby, WiFi change) faster than with the defaults (20 s / 20 s).
    PING_INTERVAL = 10.0
    PING_TIMEOUT = 5.0

    def __init__(
        self,
        core: TB_I_Core,
        disp: TB_Dispatch,
        on_action: WsActionCallback,
        host: str = "127.0.0.1",
        port: int = 0,
        ipv6_loopback: bool = True,
    ):
        self._core = core
        self._disp = disp
        self._on_action = on_action
        self._host = host
        self._port = port
        self._ipv6_loopback = ipv6_loopback
        self._servers: list[Server] = []
        self._clients = set[ServerConnection]()
        self._lastMeta: TB_WsMeta | None = None
        self._last_player_info: TB_WsPlayerInfo | None = None

        # Create the callback exactly ONCE, otherwise unsubscribe cannot find it again.
        # A typed method instead of an untyped lambda keeps the callback type fully known.
        self._player_changed_cb: Callable[[PlayerChangedData], None] = self._disp.async_callback(self._handle_player_changed)

    # ------------------------------------------------------------------ player events

    async def _handle_player_changed(self, data: PlayerChangedData) -> None:
        await self._on_player_changed(data)

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

    async def publish(self, data: PlayerChangedData):
        await self._on_player_changed(data, True)

    # ------------------------------------------------------------------ lifecycle

    async def _serve(self, host: str, port: int) -> Server:
        return await serve(
            self._handler,
            host,
            port,
            ping_interval=self.PING_INTERVAL,
            ping_timeout=self.PING_TIMEOUT,
        )

    async def start(self):
        server = await self._serve(self._host, self._port)
        self._servers.append(server)
        self._port = server.sockets[0].getsockname()[1]
        self._logger.info("WebSocket server listening on %s:%s", self._host, self._port)

        # Browsers often resolve "localhost" to ::1 first. If nobody listens there, the browser
        # waits for the failure before falling back to IPv4 (often seconds on Windows).
        # Therefore also listen on the IPv6 loopback using the same port (best effort).
        if self._ipv6_loopback and self._host == "127.0.0.1":
            try:
                server6 = await self._serve("::1", self._port)
                self._servers.append(server6)
                self._logger.info("WebSocket server listening on [::1]:%s", self._port)
            except OSError as ex:
                self._logger.debug("IPv6 loopback not available: %s", ex)

        self._core.player_changed_subscribe(self._player_changed_cb)

    async def stop(self):
        self._core.player_changed_unsubscribe(self._player_changed_cb)

        servers, self._servers = self._servers, []
        for server in servers:
            server.close()
        for server in servers:
            await server.wait_closed()

        self._clients.clear()

    # ------------------------------------------------------------------ connection handling

    async def _handler(self, websocket: ServerConnection):
        t0 = time.perf_counter()
        self._logger.info("WebSocket client connected.")
        self._clients.add(websocket)

        try:
            # Send the greeting first so a slow on_action callback cannot delay it.
            await websocket.send(self._json(TB_WsMessageTyp.CONNECTED, data={"message": "Connected to TrayBeat"}))
            self._logger.debug("CONNECTED sent after %.3f s", time.perf_counter() - t0)

            self._safe_on_action(TB_WsAction.CLIENT_CONNECT)

            async for message in websocket:
                try:
                    raw: Any = json.loads(message)
                except json.JSONDecodeError:
                    await websocket.send(self._sys_error_json("Invalid JSON"))
                    continue

                if not isinstance(raw, dict):
                    await websocket.send(self._sys_error_json("Expected a JSON object"))
                    continue

                # isinstance narrows to dict[Unknown, Unknown]; JSON object keys are always strings.
                data = cast(dict[str, Any], raw)
                await self._handle_message(websocket, data)

        except ConnectionClosed:
            self._logger.debug("WebSocket client closed the connection.")
        except Exception:
            self._logger.exception("WebSocket connection error")
        finally:
            self._clients.discard(websocket)
            # In finally so the disconnect is also reported when the connection drops abruptly.
            self._safe_on_action(TB_WsAction.CLIENT_DISCONNECT)
            self._logger.info("WebSocket client disconnected.")

    def _safe_on_action(self, action: TB_WsAction):
        """Call the callback without letting an error in it break the connection, and report slow callbacks."""
        t0 = time.perf_counter()
        try:
            self._on_action(self, action)
        except Exception:
            self._logger.exception("on_action(%s) failed", action)
        finally:
            elapsed = time.perf_counter() - t0
            if elapsed > self.SLOW_ACTION_WARN:
                self._logger.warning("on_action(%s) blocked the event loop for %.3f s", action, elapsed)

    # ------------------------------------------------------------------ messages

    def _sys_error_json(self, message: str) -> str:
        return json.dumps(asdict(TB_WsData(data_type=TB_WsMessageTyp.ERROR, data={"message": f"{message}"})))

    def _json(self, type: TB_WsMessageTyp, data: dict[str, Any]) -> str:
        return json.dumps(asdict(TB_WsData(data_type=type, data=data)))

    async def _handle_message(self, websocket: ServerConnection, data: dict[str, Any]):
        command = data.get("command")

        if command == "ping":
            await websocket.send(self._json(type=TB_WsMessageTyp.PING, data={}))
        else:
            await websocket.send(self._sys_error_json(f"Unknown command: {command}"))

    async def _send(self, client: ServerConnection, message: str):
        """Send to one client. Stuck or dead clients are removed instead of blocking the broadcast."""
        try:
            await asyncio.wait_for(client.send(message), timeout=self.SEND_TIMEOUT)
        except ConnectionClosed:
            self._clients.discard(client)
        except Exception as ex:
            self._logger.warning("Client not responding (%s), closing connection.", type(ex).__name__)
            self._clients.discard(client)
            try:
                await asyncio.wait_for(client.close(), timeout=self.SEND_TIMEOUT)
            except Exception:
                pass

    async def broadcast(self, data: dict[str, Any]):
        if not self._clients:
            return
        message = json.dumps(data)
        # Iterate over a copy because self._clients may change while sending.
        await asyncio.gather(*(self._send(client, message) for client in list(self._clients)))
