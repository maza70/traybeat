# pyright: basic
# pyright: reportUnknownMemberType=false
# pyright: reportUndefinedVariable=false
"""Expose a media player through the MPRIS D-Bus interfaces."""

import asyncio
import inspect
import logging as _logging
import time
from collections.abc import Callable
from typing import Any, TypeAlias

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import PropertyAccess, RequestNameReply
from dbus_next.service import ServiceInterface, dbus_property, method, signal
from dbus_next.signature import Variant

Callback: TypeAlias = Callable[..., Any]


class _TB_MPRISRoot(ServiceInterface):
    """Implement the ``org.mpris.MediaPlayer2`` root interface.

    The interface exposes application identity, quit/raise capabilities, and
    the URI schemes and MIME types advertised as supported by the player.
    ``Raise`` and ``Quit`` dispatch to the corresponding owner callbacks.
    """

    _owner: "TB_MPRISPlayer"

    def __init__(
        self,
        identity: str,
        desktop_entry: str,
        can_quit: bool,
        can_raise: bool,
    ) -> None:
        super().__init__("org.mpris.MediaPlayer2")
        self._identity = identity
        self._desktop_entry = desktop_entry
        self._can_quit = can_quit
        self._can_raise = can_raise

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":  # type: ignore
        return self._identity

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> "s":  # type: ignore
        return self._desktop_entry

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> "b":  # type: ignore
        return self._can_quit

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> "b":  # type: ignore
        return self._can_raise

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> "b":  # type: ignore
        return False

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":  # type: ignore
        """URI schemes advertised as supported by this player."""
        return ["file", "http", "https"]

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":  # type: ignore
        """MIME types advertised as supported by this player."""
        return [
            "audio/mpeg",
            "audio/ogg",
            "audio/flac",
            "audio/wav",
            "audio/mp4",
            "audio/x-wav",
            "audio/x-flac",
            "audio/x-vorbis+ogg",
        ]

    @method()
    def Raise(self):  # pyright: ignore[reportMissingReturnType]
        """Request that the application window be raised or activated."""
        self._owner._dispatch_callback(self._owner._on_raise)

    @method()
    def Quit(self):  # pyright: ignore[reportMissingReturnType]
        """Request that the application quit."""
        self._owner._dispatch_callback(self._owner._on_quit)

    def set_owner(self, owner: "TB_MPRISPlayer") -> None:
        self._owner = owner


class _TB_MPRISPlayerInterface(ServiceInterface):
    """Implement the ``org.mpris.MediaPlayer2.Player`` interface.

    Playback-control methods dispatch to callbacks on the owning
    :class:`TT_MPRISPlayer`. Capability properties are derived from callback
    availability. Position values and seek offsets use microseconds, as
    required by MPRIS.
    """

    def __init__(self, owner: "TB_MPRISPlayer") -> None:
        super().__init__("org.mpris.MediaPlayer2.Player")
        self._owner = owner

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":  # type: ignore
        return self._owner._playback_status  # type: ignore

    @dbus_property()
    def LoopStatus(self) -> "s":  # type: ignore
        return self._owner._loop_status

    @LoopStatus.setter
    def LoopStatus(self, value: "s"):  # type: ignore
        self._owner._dispatch_callback(self._owner._on_loop_status_changed, value)

    @dbus_property()
    def Rate(self) -> "d":  # type: ignore
        return self._owner._rate

    @Rate.setter
    def Rate(self, value: "d"):  # type: ignore
        self._owner._dispatch_callback(self._owner._on_rate_changed, value)

    @dbus_property()
    def Shuffle(self) -> "b":  # type: ignore
        return self._owner._shuffle

    @Shuffle.setter
    def Shuffle(self, value: "b"):  # type: ignore
        self._owner._dispatch_callback(self._owner._on_shuffle_changed, value)

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":  # type: ignore
        return self._owner._metadata

    @dbus_property()
    def Volume(self) -> "d":  # type: ignore
        return self._owner._volume

    @Volume.setter
    def Volume(self, value: "d"):  # type: ignore
        self._owner._dispatch_callback(self._owner._on_volume_changed, value)

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":  # type: ignore
        return self._owner._position_us

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":  # type: ignore
        return 0.25

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":  # type: ignore
        return 4.0

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":  # type: ignore
        return self._owner._on_next is not None

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":  # type: ignore
        return self._owner._on_previous is not None

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":  # type: ignore
        return self._owner._on_play is not None

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":  # type: ignore
        return self._owner._on_pause is not None

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":  # type: ignore
        return self._owner._on_seek is not None or self._owner._on_set_position is not None

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":  # type: ignore
        return True

    @method()
    def Next(self):  # pyright: ignore[reportMissingReturnType]
        """Request playback of the next track."""
        self._owner._dispatch_callback(self._owner._on_next)

    @method()
    def Previous(self):  # pyright: ignore[reportMissingReturnType]
        """Request playback of the previous track."""
        self._owner._dispatch_callback(self._owner._on_previous)

    @method()
    def Pause(self):  # pyright: ignore[reportMissingReturnType]
        """Request that playback pause."""
        self._owner._dispatch_callback(self._owner._on_pause)

    @method()
    def Play(self):  # pyright: ignore[reportMissingReturnType]
        """Request that playback start or resume."""
        self._owner._dispatch_callback(self._owner._on_play)

    @method()
    def PlayPause(self):  # pyright: ignore[reportMissingReturnType]
        """Toggle between playing and paused states based on cached status."""
        if self._owner._playback_status == "Playing":
            self._owner._dispatch_callback(self._owner._on_pause)
        else:
            self._owner._dispatch_callback(self._owner._on_play)

    @method()
    def Stop(self):  # pyright: ignore[reportMissingReturnType]
        """Request that playback stop."""
        self._owner._dispatch_callback(self._owner._on_stop)

    @method()
    def Seek(self, offset: "x"):  # type: ignore
        """Request a relative seek; offset is a signed number of microseconds."""
        self._owner._dispatch_callback(self._owner._on_seek, offset)

    @method()
    def SetPosition(
        self,
        track_id: "o",
        position: "x",  # type: ignore
    ):  # pyright: ignore[reportMissingReturnType]
        """Request an absolute position in microseconds for the given track ID."""
        current_track = self._owner._metadata.get("mpris:trackid")
        if current_track is None or track_id != current_track.value:
            return
        self._owner._dispatch_callback(self._owner._on_set_position, position)

    @method()
    def OpenUri(self, uri: "s"):  # type: ignore
        """Request playback of the supplied URI string."""
        self._owner._dispatch_callback(self._owner._on_open_uri, uri)

    @signal()
    def Seeked(self, position: "x") -> "x":  # type: ignore
        """Signal the absolute playback position after a seek, in microseconds."""
        return position


class TB_MPRISPlayer:
    """Expose a media player over the MPRIS D-Bus interfaces.

    The instance exports ``org.mpris.MediaPlayer2`` and
    ``org.mpris.MediaPlayer2.Player`` at :attr:`OBJECT_PATH` under the bus
    name ``org.mpris.MediaPlayer2.<app_id>``.

    Pass callbacks for the operations the application supports. A callback
    may be a regular callable or an async callable. Callback invocations are
    scheduled on the asyncio event loop used by :meth:`start`; callback
    exceptions are reported to that loop's exception handler. Callbacks do
    not return values to the D-Bus caller.

    Callback arguments:

    * ``on_play``, ``on_pause``, ``on_stop``, ``on_next``, ``on_previous``,
      ``on_quit``, ``on_raise``: no arguments.
    * ``on_seek(offset_us)``: signed relative seek offset in microseconds.
    * ``on_set_position(position_us)``: absolute target position in
      microseconds, for the current track only.
    * ``on_open_uri(uri)``: URI string supplied by the MPRIS client.
    * ``on_volume_changed(volume)``: requested volume as a float, normally
      in the range 0.0 to 1.0.
    * ``on_rate_changed(rate)``: requested playback rate as a float; this
      implementation advertises a supported range of 0.25 to 4.0.
    * ``on_loop_status_changed(status)``: one of ``"None"``, ``"Track"``,
      or ``"Playlist"``.
    * ``on_shuffle_changed(enabled)``: requested shuffle state as a bool.

    Property-change callbacks receive the requested value; the application
    should apply it and call the relevant ``update_*`` method to publish the
    actual state. In particular, the class does not automatically change the
    cached volume, rate, loop status, or shuffle state when a setter callback
    is dispatched.

    Call :meth:`start` and :meth:`stop` from the asyncio event-loop thread.
    State-update methods may be called from another thread; updates are then
    scheduled thread-safely on the event loop. If a callback needs to access
    a GLib-owned GStreamer pipeline, bridge to that context (for example with
    ``GLib.idle_add``) rather than accessing it directly from asyncio.
    """

    OBJECT_PATH = "/org/mpris/MediaPlayer2"
    BUS_NAME_PREFIX = "org.mpris.MediaPlayer2."
    _logger = _logging.getLogger(__name__)

    def __init__(
        self,
        app_id: str,
        identity: str,
        desktop_entry: str = "",
        on_play: Callback | None = None,
        on_pause: Callback | None = None,
        on_stop: Callback | None = None,
        on_seek: Callback | None = None,
        on_set_position: Callback | None = None,
        on_next: Callback | None = None,
        on_previous: Callback | None = None,
        on_open_uri: Callback | None = None,
        on_volume_changed: Callback | None = None,
        on_rate_changed: Callback | None = None,
        on_loop_status_changed: Callback | None = None,
        on_shuffle_changed: Callback | None = None,
        on_quit: Callback | None = None,
        on_raise: Callback | None = None,
    ) -> None:
        """Create the MPRIS service and register application callbacks.

        Args:
            app_id: D-Bus name suffix appended to
                ``org.mpris.MediaPlayer2.``. Each dot-separated component
                must start with a letter or underscore and contain only
                letters, digits, or underscores.
            identity: Human-readable application name exposed as MPRIS
                ``Identity``.
            desktop_entry: Desktop entry name exposed as ``DesktopEntry``;
                defaults to ``app_id`` when empty.
            on_play: Called without arguments when playback should start.
            on_pause: Called without arguments when playback should pause.
            on_stop: Called without arguments when playback should stop.
            on_seek: Called with a signed relative offset in microseconds.
            on_set_position: Called with an absolute position in microseconds
                for the current track.
            on_next: Called without arguments to advance to the next track.
            on_previous: Called without arguments to select the previous track.
            on_open_uri: Called with the URI string passed to ``OpenUri``.
            on_volume_changed: Called with the requested volume (float).
            on_rate_changed: Called with the requested playback rate (float).
            on_loop_status_changed: Called with ``"None"``, ``"Track"``, or
                ``"Playlist"``.
            on_shuffle_changed: Called with the requested shuffle bool.
            on_quit: Called without arguments when a client requests ``Quit``.
            on_raise: Called without arguments when a client requests ``Raise``.

        Callbacks may be synchronous or asynchronous. ``None`` means that
        the callback is not provided and usually makes the corresponding
        capability property false. ``CanControl`` is currently always true.

        Raises:
            ValueError: If ``app_id`` is empty or contains invalid components.
        """
        if not app_id or any(not part for part in app_id.split(".")):
            raise ValueError("app_id must be a non-empty D-Bus name suffix")
        if any(not (part[0].isalpha() or part[0] == "_") for part in app_id.split(".")):
            raise ValueError("Each app_id component must start with a letter or underscore")
        if any(not all(char.isalnum() or char == "_" for char in part) for part in app_id.split(".")):
            raise ValueError("app_id may contain only letters, digits, and underscores")

        self.app_id = app_id
        self.bus_name = f"{self.BUS_NAME_PREFIX}{app_id}"
        self.identity = identity
        self.desktop_entry = desktop_entry or app_id

        self._on_play = on_play
        self._on_pause = on_pause
        self._on_stop = on_stop
        self._on_seek = on_seek
        self._on_set_position = on_set_position
        self._on_next = on_next
        self._on_previous = on_previous
        self._on_open_uri = on_open_uri
        self._on_volume_changed = on_volume_changed
        self._on_rate_changed = on_rate_changed
        self._on_loop_status_changed = on_loop_status_changed
        self._on_shuffle_changed = on_shuffle_changed
        self._on_quit = on_quit
        self._on_raise = on_raise

        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._started = False

        self._playback_status = "Stopped"
        self._loop_status = "None"
        self._rate = 1.0
        self._shuffle = False
        self._volume = 1.0
        self._position_us = 0
        self._position_updated_at = time.monotonic()
        self._track_id = "/org/mpris/MediaPlayer2/Track/0"
        self._metadata: dict[str, Variant] = {
            "mpris:trackid": Variant("o", self._track_id),
        }

        self._root_interface = _TB_MPRISRoot(
            identity=self.identity,
            desktop_entry=self.desktop_entry,
            can_quit=self._on_quit is not None,
            can_raise=self._on_raise is not None,
        )
        self._root_interface.set_owner(self)
        self._player_interface = _TB_MPRISPlayerInterface(self)

    async def start(self) -> None:
        """Connect to the session bus and export both MPRIS interfaces.

        This method is idempotent. It must run inside the asyncio event loop
        that will be used to dispatch callbacks and state updates.

        Raises:
            RuntimeError: If the MPRIS bus name cannot be acquired.
            Exception: Propagates D-Bus connection or name-acquisition errors.
        """
        if self._started:
            return

        loop = asyncio.get_running_loop()
        bus = await MessageBus().connect()
        bus.export(self.OBJECT_PATH, self._root_interface)
        bus.export(self.OBJECT_PATH, self._player_interface)

        try:
            reply = await bus.request_name(self.bus_name)
            if reply not in (
                RequestNameReply.PRIMARY_OWNER,
                RequestNameReply.ALREADY_OWNER,
            ):
                raise RuntimeError(f"Could not acquire D-Bus name {self.bus_name}: {reply}")
        except Exception:
            bus.unexport(self.OBJECT_PATH, self._player_interface)
            bus.unexport(self.OBJECT_PATH, self._root_interface)
            bus.disconnect()
            raise

        self._loop = loop
        self._bus = bus
        self._started = True

    async def stop(self) -> None:
        """Unexport both interfaces and disconnect from the session bus.

        Calling this method when the service is already stopped has no effect.
        """

        bus = self._bus
        if not self._started or bus is None:
            return
        await bus.release_name(self.bus_name)
        bus.unexport(self.OBJECT_PATH, self._player_interface)
        bus.unexport(self.OBJECT_PATH, self._root_interface)
        bus.disconnect()
        self._bus = None
        self._started = False
        self._loop = None

    def _dispatch_callback(self, callback: Callback | None, *args: Any) -> None:
        """Dispatch a callback on the service's asyncio event loop.

        ``args`` are passed to the callback unchanged. Missing callbacks and
        calls made before startup or after shutdown are ignored. Awaitable
        results are scheduled as asyncio tasks. Exceptions are sent to the
        event loop's exception handler rather than returned over D-Bus.
        """
        if callback is None:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def invoke() -> None:
            try:
                result = callback(*args)
                if inspect.isawaitable(result):
                    task = asyncio.ensure_future(result, loop=loop)
                    task.add_done_callback(self._handle_task_result)
            except Exception as exc:
                loop.call_exception_handler(
                    {
                        "message": "Exception in MPRIS callback",
                        "exception": exc,
                        "callback": callback,
                    }
                )

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is loop:
            invoke()
        else:
            loop.call_soon_threadsafe(invoke)

    @staticmethod
    def _handle_task_result(task: asyncio.Future[Any]) -> None:
        """Report an asynchronous callback's exception to its event loop."""
        if task.cancelled():
            return
        exception = task.exception()
        if exception is not None:
            loop = task.get_loop()
            loop.call_exception_handler(
                {
                    "message": "Exception in asynchronous MPRIS callback",
                    "exception": exception,
                    "task": task,
                }
            )

    def _run_on_loop(self, callback: Callable[[], None]) -> None:
        """Run a state update on the service event loop, thread-safely.

        Raises:
            RuntimeError: If the service has not been started or is stopped.
        """
        loop = self._loop
        if not self._started or loop is None or loop.is_closed():
            raise RuntimeError("TT_MPRISPlayer.start() has not been called")

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is loop:
            callback()
        else:
            loop.call_soon_threadsafe(callback)

    def _notify_properties(
        self,
        interface: str,
        changed: dict[str, Any],
        invalidated: list[str] | None = None,
    ) -> None:
        """Emit a D-Bus ``PropertiesChanged`` signal.

        Args:
            interface: Full D-Bus interface name to notify.
            changed: Property names and their new values.
            invalidated: Optional property names whose values should be
                re-read by clients instead of being included in the signal.
        """
        if not self._started or self._bus is None:
            return
        interfaces: dict[str, ServiceInterface] = {
            self._root_interface.name: self._root_interface,
            self._player_interface.name: self._player_interface,
        }
        target = interfaces.get(interface)
        if target is None:
            raise ValueError(f"Unknown interface: {interface}")
        target.emit_properties_changed(changed, invalidated or [])

    def update_status(self, status: str) -> None:
        """Publish the current playback state.

        Args:
            status: Exactly ``"Playing"``, ``"Paused"``, or ``"Stopped"``.

        Emits a ``PlaybackStatus`` property-change notification.

        Raises:
            ValueError: If ``status`` is not one of the supported values.
        """
        if status not in ("Playing", "Paused", "Stopped"):
            raise ValueError("status must be Playing, Paused, or Stopped")

        def update() -> None:
            self._playback_status = status
            self._position_updated_at = time.monotonic()
            self._notify_properties(
                "org.mpris.MediaPlayer2.Player",
                {"PlaybackStatus": status},
            )

        self._run_on_loop(update)

    def update_metadata(
        self,
        title: str = "",
        artist: str | list[str] | tuple[str, ...] | None = None,
        album: str = "",
        length_us: int = 0,
        art_url: str = "",
        track_number: int = 0,
        url: str = "",
        track_id: str | None = None,
    ) -> None:
        """Publish metadata for the current track.

        Args:
            title: Track title; omitted from metadata when empty.
            artist: One artist name or a sequence of artist names.
            album: Album title; omitted when empty.
            length_us: Track length in microseconds; included only if positive.
            art_url: Artwork URI, usually a ``file://`` or ``https://`` URI.
            track_number: Track number; included only if positive.
            url: Track URI stored as ``xesam:url``; omitted when empty.
            track_id: Optional D-Bus object path identifying the track. If
                omitted or empty, a new path is generated. Supply a valid
                object path because MPRIS metadata uses the D-Bus ``o`` type.

        Only non-empty optional fields are included. The method replaces the
        complete metadata dictionary and emits a ``Metadata`` notification.
        Time values are in microseconds, not seconds.
        """

        def update() -> None:
            new_track_id = track_id or self._new_track_id()
            metadata: dict[str, Variant] = {"mpris:trackid": Variant("o", new_track_id)}
            if title:
                metadata["xesam:title"] = Variant("s", title)
            if artist:
                artists = [artist] if isinstance(artist, str) else list(artist)
                metadata["xesam:artist"] = Variant("as", artists)
            if album:
                metadata["xesam:album"] = Variant("s", album)
            if length_us > 0:
                metadata["mpris:length"] = Variant("x", int(length_us))
            if art_url:
                metadata["mpris:artUrl"] = Variant("s", art_url)
            if track_number > 0:
                metadata["xesam:trackNumber"] = Variant("i", int(track_number))
            if url:
                metadata["xesam:url"] = Variant("s", url)

            self._track_id = new_track_id
            self._metadata = metadata
            #  self._logger.debug("Published metadata: %r", self._metadata)
            self._notify_properties("org.mpris.MediaPlayer2.Player", {"Metadata": metadata})

        self._run_on_loop(update)

    @staticmethod
    def _new_track_id() -> str:
        """Generate a track object path using the monotonic clock."""
        return f"/org/mpris/MediaPlayer2/Track/{time.monotonic_ns()}"

    def update_position(self, position_us: int) -> None:
        """Update the cached position, in microseconds, without a Seeked signal.

        Negative positions are clamped to zero. The updated position is
        available through the MPRIS ``Position`` property.
        """

        def update() -> None:
            self._position_us = max(0, int(position_us))
            self._position_updated_at = time.monotonic()

        self._run_on_loop(update)

    def emit_seeked(self, position_us: int) -> None:
        """Update the cached position and emit MPRIS ``Seeked``.

        Args:
            position_us: New absolute playback position in microseconds.

        Negative positions are clamped to zero. Call this after a seek has
        actually taken effect so clients can synchronize their position.
        """

        def update() -> None:
            self._position_us = max(0, int(position_us))
            self._position_updated_at = time.monotonic()
            self._player_interface.Seeked(self._position_us)

        self._run_on_loop(update)

    def update_volume(self, volume: float) -> None:
        """Publish the actual volume, clamped to the range 0.0–1.0.

        Emits a ``Volume`` property-change notification. This method reports
        the player's actual state; it does not invoke ``on_volume_changed``.
        """

        def update() -> None:
            self._volume = max(0.0, min(1.0, float(volume)))
            self._notify_properties(
                "org.mpris.MediaPlayer2.Player",
                {"Volume": self._volume},
            )

        self._run_on_loop(update)

    def update_rate(self, rate: float) -> None:
        """Publish the actual playback rate.

        Args:
            rate: Playback rate between 0.25 and 4.0, inclusive.

        Emits a ``Rate`` property-change notification.

        Raises:
            ValueError: If ``rate`` is outside the advertised range.
        """
        if not 0.25 <= rate <= 4.0:
            raise ValueError("rate must be between 0.25 and 4.0")

        def update() -> None:
            self._rate = float(rate)
            self._notify_properties(
                "org.mpris.MediaPlayer2.Player",
                {"Rate": self._rate},
            )

        self._run_on_loop(update)

    def update_loop_status(self, status: str) -> None:
        """Publish the actual repeat mode.

        Args:
            status: One of ``"None"``, ``"Track"``, or ``"Playlist"``.

        Emits a ``LoopStatus`` property-change notification.

        Raises:
            ValueError: If ``status`` is not supported.
        """
        if status not in ("None", "Track", "Playlist"):
            raise ValueError("status must be None, Track, or Playlist")

        def update() -> None:
            self._loop_status = status
            self._notify_properties(
                "org.mpris.MediaPlayer2.Player",
                {"LoopStatus": status},
            )

        self._run_on_loop(update)

    def update_shuffle(self, enabled: bool) -> None:
        """Publish whether shuffle is enabled and notify MPRIS clients."""

        def update() -> None:
            self._shuffle = bool(enabled)
            self._notify_properties(
                "org.mpris.MediaPlayer2.Player",
                {"Shuffle": self._shuffle},
            )

        self._run_on_loop(update)

    def update_capabilities(self) -> None:
        """Notify clients that playback capabilities may have changed.

        Call this after changing callback availability at runtime. The
        capability properties are derived from whether their callbacks are
        ``None``; this method invalidates those properties so clients fetch
        their new values. It does not itself change any callback.
        """

        def update() -> None:
            self._notify_properties(
                "org.mpris.MediaPlayer2.Player",
                {},
                [
                    "CanGoNext",
                    "CanGoPrevious",
                    "CanPlay",
                    "CanPause",
                    "CanSeek",
                ],
            )

        self._run_on_loop(update)
