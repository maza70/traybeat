"""Local HTTP server for the TrayBeat information page and station editor."""

from __future__ import annotations

import copy
import json
import logging
import re
import threading
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum, auto
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from urllib.parse import ParseResult, parse_qs, urlparse

from traybeat.gui.tb_resource import TB_Resource
from traybeat.lib.tb_const import APP_VERSION, TEMP_PATH


class TB_HttpAction(StrEnum):
    STATION_CONFIG_CHANGED = auto()
    PLAYER_PLAY = auto()
    PLAYER_PAUSE = auto()
    PLAYER_STOP = auto()
    PLAYER_NEXT = auto()
    PLAYER_PREVIOUS = auto()
    PLAYER_VOLUME_UP = auto()
    PLAYER_VOLUME_DOWN = auto()
    PLAYER_WS_DATA = auto()
    """ send player data over websocket  """


HttpActionCallback = Callable[["TB_HttpServer", TB_HttpAction], None]


class TB_HttpServer:
    """Serve the TrayBeat web UI and expose the complete configuration as JSON."""

    _logger = logging.getLogger(__name__)
    MAX_REQUEST_BYTES = 1_000_000

    def __init__(
        self,
        config: dict[str, Any],
        host: str = "127.0.0.1",
        port: int = 0,
        on_action: HttpActionCallback | None = None,
    ) -> None:

        self._nonce = str(uuid.uuid4())
        self._template_vars: dict[str, str] = {"NONCE": self._nonce}
        self.host = host
        self.port = port
        self._lock = threading.RLock()
        self._config = copy.deepcopy(config)
        self._thread: threading.Thread | None = None
        self._closed = False
        self._logger.info("Start webserver")
        self._httpd = ThreadingHTTPServer((self.host, self.port), self._make_handler())
        self._httpd.daemon_threads = True
        self._on_action = on_action
        self._callback_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="TrayBeatCallback",
        )

    @property
    def config(self) -> dict[str, Any]:
        """Return a copy of the current configuration JSON value."""
        with self._lock:
            return copy.deepcopy(self._config)

    @config.setter
    def config(self, value: dict[str, Any]) -> None:
        """Replace the complete configuration without schema validation."""
        with self._lock:
            self._config = copy.deepcopy(value)

    @property
    def template_vars(self) -> Mapping[str, str]:
        return MappingProxyType(self._template_vars)

    @property
    def address(self) -> str:
        """Return the base URL of the listening server."""
        host, port = self._httpd.server_address[:2]
        display_host = f"[{host}]" if ":" in host else host  # type: ignore
        return f"http://{display_host}:{port}"

    @property
    def nonce(self) -> str:
        """the nonce for Content-Security-Policy."""

        return self._nonce

    @property
    def station_url(self) -> str:
        return f"{self.address}/stations.html"

    @property
    def about_url(self) -> str:
        return f"{self.address}/index.html"

    @property
    def player_controls_url(self) -> str:
        return f"{self.address}/player.html"

    def _replace_template_vars(self, template: str) -> str:
        # is a variable in the html?
        if re.search(r"\{\S+\}", template):
            for name, value in self.template_vars.items():
                template = template.replace(f"{{{name}}}", value)
        return template

    def _make_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"TrayBeat/{APP_VERSION}"
            sys_version = ""

            def log_message(self, format: str, *args: object) -> None:
                # Suppress HTTP access logs.
                pass

            def _send(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _send_json(self, status: int, value: object) -> None:
                try:
                    data = json.dumps(value, ensure_ascii=False).encode("utf-8")
                except (TypeError, ValueError):
                    self._send(
                        500,
                        b'{"error":"The configuration is not JSON serializable."}',
                        "application/json; charset=utf-8",
                    )
                    return
                self._send(status, data, "application/json; charset=utf-8")

            def _get_mimetype(self, filename: Path) -> str:
                match filename.suffix.lower():
                    case ".js":
                        return "text/javascript; charset=utf-8"
                    case ".html":
                        return "text/html; charset=utf-8"
                    case ".css":
                        return "text/css; charset=utf-8"
                    case ".ico":
                        return "image/x-icon"
                    case ".svg":
                        return "image/svg+xml"
                    case ".png":
                        return "image/png"
                    case ".jpg":
                        return "image/jpeg"
                    case _:
                        return "text/plain; charset=utf-8"

            def _send_template_file(self, filename: Path) -> None:
                try:
                    content = TB_Resource.get_bytes("html", filename.name)
                    html = content.decode("utf-8")
                    # is a variable in the html?
                    if re.search(r"\{\S+\}", html):
                        for name, value in owner.template_vars.items():
                            html = html.replace(f"{{{name}}}", value)
                        content = html.encode("utf-8")

                except OSError:
                    self._send(
                        500,
                        b"Web interface file is missing or cannot be read.",
                        "text/plain; charset=utf-8",
                    )
                    return

                self._send(200, content, self._get_mimetype(filename))

            def _send_file(self, filename: Path) -> None:
                try:
                    if filename.exists():
                        self._send(200, filename.read_bytes(), self._get_mimetype(filename))
                    else:
                        self._send(500, b"File cannot be read.", "text/plain; charset=utf-8")
                except OSError:
                    self._send(500, b"File cannot be read.", "text/plain; charset=utf-8")
                    return

            def _send_resource(self, filename: Path) -> None:
                try:
                    content = TB_Resource.get_bytes(
                        str(filename.parent),
                        filename.name,
                    )

                    self._send(200, content, self._get_mimetype(filename))
                except OSError:
                    self._send(500, b"File cannot be read.", "text/plain; charset=utf-8")
                    return

            def _read_json_body(self) -> object:
                content_type = self.headers.get("Content-Type", "")
                media_type = content_type.split(";", 1)[0].strip().lower()
                if media_type != "application/json":
                    raise ValueError("Content-Type must be application/json.")

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError as exc:
                    raise ValueError("Invalid Content-Length header.") from exc

                if length <= 0:
                    raise ValueError("Request body must not be empty.")
                if length > owner.MAX_REQUEST_BYTES:
                    raise ValueError("Request body is too large.")

                raw_body = self.rfile.read(length)
                if len(raw_body) != length:
                    raise ValueError("Incomplete request body.")

                try:
                    return json.loads(raw_body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"Invalid JSON: {exc}") from exc

            def _player_cmd(self, url: ParseResult):
                params = parse_qs(url.query)
                cmd = params.get("cmd", [None])[0]
                match cmd:
                    case "play":
                        owner._invoke_action(TB_HttpAction.PLAYER_PLAY)
                    case "stop":
                        owner._invoke_action(TB_HttpAction.PLAYER_STOP)
                    case "pause":
                        owner._invoke_action(TB_HttpAction.PLAYER_PAUSE)
                    case "next":
                        owner._invoke_action(TB_HttpAction.PLAYER_NEXT)
                    case "prev":
                        owner._invoke_action(TB_HttpAction.PLAYER_PREVIOUS)
                    case "vol_up":
                        owner._invoke_action(TB_HttpAction.PLAYER_VOLUME_UP)
                    case "vol_down":
                        owner._invoke_action(TB_HttpAction.PLAYER_VOLUME_DOWN)
                    case "player-data":
                        owner._invoke_action(TB_HttpAction.PLAYER_WS_DATA)
                    case _:
                        self._send(500, b"unknown command.", "text/plain; charset=utf-8")
                        return
                self._send(200, b"OK", "text/plain; charset=utf-8")

            def do_GET(self) -> None:
                url = urlparse(self.path)

                if url.path == "/":
                    self._send_template_file(Path("index.html"))
                elif url.path == "/api/config":
                    self._send_json(200, owner.config)
                elif url.path.startswith("/api/cover/") or url.path.startswith("/api/cover/"):
                    p = Path(TEMP_PATH, Path(url.path).name)
                    self._send_file(p)
                elif url.path == "/api/player":
                    p = Path(TEMP_PATH, Path(url.path).name)
                    self._player_cmd(url)
                else:
                    p = Path(url.path)
                    if p.suffix == ".html" or p.suffix == ".js" or p.suffix == ".css":
                        # this files can contain variables
                        self._send_template_file(p)
                    else:
                        self._send_resource(p)

            def do_PUT(self) -> None:
                if urlparse(self.path).path != "/api/config":
                    self._send_json(404, {"error": "Not found."})
                    return

                try:
                    # The client validates the document; the server only parses JSON
                    # and stores the complete value in the config property.
                    document = self._read_json_body()
                    owner.config = cast(dict[str, Any], document)
                    self._send_json(200, {"ok": True, "config": owner.config})
                    owner._invoke_action(TB_HttpAction.STATION_CONFIG_CHANGED)

                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})

        return Handler

    def _invoke_action(self, action: TB_HttpAction):
        """Schedule the callback without blocking the HTTP request."""
        if self._on_action is None:
            return
        self._callback_executor.submit(
            self._on_action,
            self,
            action,
        )

    def set_template_var(self, var_name: str, value: str | None):
        if value is None and self._template_vars.get(var_name) is not None:
            self._template_vars.pop(var_name)
            return
        if value is not None:
            self._template_vars[var_name] = value

    def start(self) -> None:
        """Start serving requests in a daemon thread."""
        if self._closed:
            raise RuntimeError("This server has been stopped and cannot be restarted.")
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="TrayBeatHTTP",
            daemon=True,
        )
        self._thread.start()
        self._logger.info(f"Internal webserver runs now under {self._httpd.server_address}")

    def stop(self) -> None:
        """Stop the server and release its listening socket."""
        if self._closed:
            return
        if self._thread is not None and self._thread.is_alive():
            self._httpd.shutdown()
            self._thread.join(timeout=5)
        self._httpd.server_close()
        self._closed = True
        self._thread = None
