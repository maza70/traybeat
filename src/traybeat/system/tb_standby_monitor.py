import asyncio
import logging
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Any

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import BusType

from traybeat.lib.tb_i_core import PlayerChangedData, TB_CorePlayerState, TB_I_Core


class TB_StandbyMonitor:
    """Monitor system suspend and resume events via D-Bus."""

    _logger = logging.getLogger(__name__)

    def __init__(
        self,
        core: TB_I_Core,
        on_sleep: Callable[[], Any | None] | None = None,
        on_wakeup: Callable[[Any, TB_CorePlayerState], None] | None = None,
    ):
        self._core = core
        self._on_sleep = on_sleep
        self._on_wakeup = on_wakeup
        self._appState: Any = None
        self._player_last_state: TB_CorePlayerState = TB_CorePlayerState.UNKNOWN
        self._wakeup_state: TB_CorePlayerState = TB_CorePlayerState.UNKNOWN
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def _on_player_changed(self, data: PlayerChangedData):
        if data.player_info is not None:
            # we have the problem that gstreamer set the state tu pause when suspend start, need to known with state was the plaer before start the suspend
            if self._player_last_state != data.player_info.state:
                self._player_last_state = data.player_info.state

    def start(self) -> None:
        """Start monitoring in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="SleepMonitor",
            daemon=True,
        )
        self._thread.start()
        self._core.player_changed_subscribe(lambda data: self._on_player_changed(data))

    def stop(self) -> None:
        """Stop monitoring and wait for the background thread."""
        self._core.player_changed_unsubscribe(lambda data: self._on_player_changed(data))
        self._stop_event.set()

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _run(self) -> None:
        """Run the asyncio event loop."""
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._connect())
            loop.run_forever()
        finally:
            loop.close()
            self._loop = None

    async def _connect(self) -> None:
        """Connect to system D-Bus and register the signal handler."""
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        introspection = await bus.introspect(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
        )

        proxy = bus.get_proxy_object(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            introspection,
        )

        interface = proxy.get_interface("org.freedesktop.login1.Manager")
        interface.on_prepare_for_sleep(self._handle_prepare_for_sleep)  # type: ignore

        self._bus = bus

    def _handle_prepare_for_sleep(self, sleeping: bool) -> None:
        """Dispatch suspend and resume callbacks."""

        if sleeping:
            if self._on_sleep is not None:
                self._wakeup_state = self._player_last_state
                self._appState = self._on_sleep()
        else:
            if self._on_wakeup is not None:
                self._logger.debug(f"system wakeup set player state to {self._wakeup_state}")
                self._on_wakeup(self._appState, self._wakeup_state)

    def __enter__(self):
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ):
        self.stop()
