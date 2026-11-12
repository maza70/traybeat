"""Audio player based on GStreamer and PyGObject.

Supports web radio, M3U/M3U8 playlists, metadata callbacks,
volume control, mute and automatic reconnection.

A running GLib MainLoop is required.
"""

from __future__ import annotations

import logging
import os
import random as _random
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import gi

from traybeat.lib.tb_const import APP_ICON, APP_ID, APP_NAME

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # type: ignore

MetadataCallback = Callable[[Any], None]
CoverCallback = Callable[[bytes], None]


class TB_PlayerStatus(StrEnum):
    """Describe the internal playback status of :class:`TT_Player`.

    This is a ``StrEnum``: each member is also a string whose value is the
    lowercase member name, for example ``"playing"``. Comparisons with plain
    strings such as ``status == "playing"`` therefore keep working.

    Members:
        STOPPED: Playback is stopped or has finished.
        CONNECTING: A connection to the source is being established.
        PLAYING: Playback is running.
        PAUSED: Playback is paused.
        BUFFERING: The pipeline is buffering data.
        RECONNECTING: A reconnection attempt is scheduled.
        ERROR: A stream or pipeline error occurred.
        MUTED: The player is muted. This is reported by
            :attr:`TT_Player.status` and :meth:`TT_Player.get_status` while
            mute is enabled, regardless of the underlying playback state.
    """

    STOPPED = auto()
    CONNECTING = auto()
    PLAYING = auto()
    PAUSED = auto()
    BUFFERING = auto()
    RECONNECTING = auto()
    ERROR = auto()
    MUTED = auto()


StatusCallback = Callable[[TB_PlayerStatus, TB_PlayerStatus], None]
"""Called with ``(old_status, new_status)`` when :attr:`TT_Player.status` changes."""


@dataclass
class PlayerStatus:
    status: TB_PlayerStatus
    mode: str
    url: str | None
    playlist_index: int
    playlist_length: int
    volume: float
    volume_delta: float
    muted: bool
    reconnect_attempt: int
    gst_state: str
    playlist_song_position: float = 0.0
    playlist_song_duration: float = 0.0


class TB_Player:
    """Play web radio streams, media files, and M3U/M3U8 playlists.

    The player uses a GStreamer ``playbin`` pipeline. It supports metadata and
    cover-art notifications, volume and mute control, and automatic
    reconnection after stream failures.

    Callbacks:
        ``on_metadata`` is called when received metadata changes.
        ``on_cover`` is called when new embedded cover-art bytes are received.
        ``on_status_changed`` is called with ``(old, new)`` whenever the value
        of :attr:`status` changes, including ``TT_PlayerStatus.MUTED`` when
        mute is switched on or off.

    Args:
        on_metadata: Optional callback receiving changed metadata dictionaries.
        use_glib_mainloop: Start an internal GLib main loop in a daemon thread.
            Set to ``False`` when the application already runs a GLib main loop.
        reconnect_delay: Initial automatic reconnection delay, in seconds.
        max_reconnects: Maximum number of consecutive reconnection attempts.
        on_cover: Optional callback receiving encoded cover-art data as bytes.
        on_status_changed: Optional callback receiving the old and the new
            :class:`TT_PlayerStatus` whenever :attr:`status` changes.

    Raises:
        RuntimeError: If GStreamer cannot create the ``playbin`` element.

    A running GLib main loop is required to process GStreamer bus messages and
    reconnection timers. GTK applications normally provide one.
    """

    _player: Gst.Element
    _logger = logging.getLogger(__name__)

    def __init__(
        self,
        on_metadata: MetadataCallback | None = None,
        use_glib_mainloop: bool = True,
        reconnect_delay: int = 3,
        max_reconnects: int = 99,
        on_status_changed: StatusCallback | None = None,
    ) -> None:
        """Initialize GStreamer and create the playback pipeline.

        Args:
            on_metadata: Callback invoked when metadata changes.
            reconnect_delay: Initial reconnection delay in seconds.
            max_reconnects: Maximum number of consecutive reconnection attempts.
            on_cover: Optional callback invoked with cover image data as bytes.
                The callback is called when a new embedded cover is received.
            on_status_changed: Optional callback invoked as
                ``callback(old_status, new_status)`` whenever :attr:`status`
                changes. It runs in the context that caused the change, so
                usually in the GLib main loop; exceptions are caught and
                printed.
        """

        Gst.init(None)
        GLib.set_application_name(APP_NAME)
        GLib.set_prgname(APP_ID)

        props = Gst.Structure.new_empty("props")
        props.set_value("application.name", APP_NAME)
        props.set_value("application.id", APP_ID)
        props.set_value("application.icon_name", APP_ICON)
        props.set_value("media.role", "music")

        sink = Gst.ElementFactory.make("pulsesink", "audio-sink")
        if sink is None:
            raise RuntimeError("pulsesink element 'audio-sink' is unavailable.")
        sink.set_property("client-name", APP_NAME)
        sink.set_property("stream-properties", props)

        player = Gst.ElementFactory.make("playbin", "audio-player")
        if player is None:
            raise RuntimeError("playbin element 'audio-player' is unavailable.")
        self._player = player
        self._player.connect("source-setup", self._on_source_setup)

        self._player.set_property("audio-sink", sink)

        self._callback = on_metadata
        self._status_callback = on_status_changed
        self._last_cover: bytes | None = None
        self._volume = 1.0
        self._volume_delta = 0
        self._muted = False
        self._last_error = ""
        self._mode = "idle"
        self._url: str | None = None
        self._playlist: list[dict[str, str]] = []
        self._index = -1
        self._previous_index = -1
        # Start position (seconds) given to load_playlist(); consumed by the
        # next playlist entry that is started.
        self._resume_position: float | None = None
        # Position (seconds) to seek to as soon as the pipeline has prerolled.
        self._pending_seek: float | None = None
        self._playback_status: TB_PlayerStatus = TB_PlayerStatus.STOPPED
        # Status, der vor einer BUFFERING-Phase aktiv war (wird danach wiederhergestellt).
        self._status_before_buffering: TB_PlayerStatus = TB_PlayerStatus.CONNECTING

        self._reconnect_delay = max(1, reconnect_delay)
        self._max_reconnects = max(0, max_reconnects)
        self._reconnect_attempt = 0
        self._reconnect_source: int | None = None
        self._stopping = False
        self._disposed = False

        bus = self._player.get_bus()
        if bus is None:
            raise RuntimeError("can't get audio-player bus")
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)
        self._apply_volume()
        if use_glib_mainloop:
            self._start_mainloop()

    @property
    def volume(self) -> float:
        """Get or set the volume between 0.0 and 1.0."""
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError("Volume must be between 0.0 and 1.0.")

        value = float(value)
        old_value = self._volume
        if value == old_value:
            return
        self._volume = value
        self._apply_volume()

    @property
    def volume_delta(self) -> float:
        """Get or set the volume between 0.0 and 1.0."""
        return self._volume_delta

    @volume_delta.setter
    def volume_delta(self, value: float) -> None:
        value = float(value)

        self._volume_delta = value
        self._apply_volume()

    @property
    def last_error(self) -> str:
        """the last error."""
        return self._last_error

    @property
    def is_muted(self) -> bool:
        """Return whether mute is enabled."""
        return self._muted

    @property
    def status(self) -> TB_PlayerStatus:
        """Return the externally visible player status.

        While mute is enabled this is ``TT_PlayerStatus.MUTED``. Otherwise it
        is the current playback status. The internal ``_status`` always holds
        the real playback state, because pause handling depends on it.
        """
        if self._muted:
            return TB_PlayerStatus.MUTED
        return self._status

    @property
    def _status(self) -> TB_PlayerStatus:
        """Return the real playback status, ignoring mute."""
        return self._playback_status

    @_status.setter
    def _status(self, value: TB_PlayerStatus) -> None:
        """Set the playback status and notify ``on_status_changed``."""
        old_status = self.status
        self._playback_status = value
        self._notify_status_changed(old_status)

    def _on_source_setup(self, playbin: Gst.Element, source: Gst.Element):
        self._logger.debug("GStreamer source: %s", source.get_name())

        if source.find_property("timeout"):  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            source.set_property("timeout", 5)
            self._logger.debug("Source timeout set to 5 seconds")

    def _apply_volume(self) -> None:
        """Apply the current volume and mute settings to GStreamer."""
        adjustedVolume = self._volume + self._volume_delta
        adjustedVolume = min(adjustedVolume, 1)
        adjustedVolume = max(adjustedVolume, 0)

        self._player.set_property("volume", adjustedVolume)
        self._player.set_property("mute", self._muted)

    def mute(self, enabled: bool | None = None) -> bool:
        """Enable or disable mute.

        If enabled is omitted, toggle the current mute state.

        Returns:
            The new mute state.
        """
        old_value = self._muted
        old_status = self.status
        self._muted = not self._muted if enabled is None else bool(enabled)
        self._apply_volume()
        if self._muted != old_value:
            self._notify_status_changed(old_status)
        return self._muted

    @staticmethod
    def _to_uri(source: str | Path) -> str:
        """Convert a local file path to a URI.

        Existing URIs, such as HTTP and HTTPS URLs, are preserved.
        Local paths are expanded and resolved to absolute paths.
        """
        value = os.fspath(source)
        parsed = urlparse(value)

        if parsed.scheme and len(parsed.scheme) > 1:
            return value

        return Path(value).expanduser().resolve().as_uri()

    def _start_mainloop(self) -> None:
        """Start the GLib main loop in a background thread.

        Creates a new GLib MainLoop and runs it in a dedicated daemon
        thread. This allows GStreamer bus messages, including metadata
        updates, to be processed without blocking the calling thread.

        If the main loop is already running in its thread, this method
        does nothing.

        Note:
            Call this method before starting playback if no other GLib
            main loop is running in the application.
        """
        if hasattr(self, "_mainloop_thread") and self._mainloop_thread.is_alive():
            return

        self._mainloop = GLib.MainLoop()
        self._mainloop_thread = threading.Thread(
            target=self._mainloop.run,
            name="GPlayer-GLib",
            daemon=True,
        )
        self._mainloop_thread.start()

    def _stop_mainloop(self) -> None:
        """Stop the GLib main loop and wait for its thread to finish.

        Requests the main loop to quit if it is running, then waits for
        the background thread to terminate, up to two seconds.

        This method does nothing if the main loop or its thread has not
        been created.

        Note:
            Stopping the main loop stops the processing of GStreamer bus
            messages and metadata callbacks. Stop playback and release
            player resources separately if necessary.
        """
        loop = getattr(self, "_mainloop", None)
        thread = getattr(self, "_mainloop_thread", None)

        if loop is not None and loop.is_running():
            loop.quit()

        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

    def play_url(self, url: str) -> None:
        """Start a web radio stream or a single media file."""
        try:
            self._cancel_reconnect()
            self._stopping = False
            self._last_error = ""
            self._mode = "radio" if urlparse(url).scheme in {"http", "https", "icy"} else "single"
            self._url = url
            self._index = -1
            self._resume_position = None
            self._pending_seek = None
            self._reconnect_attempt = 0
            self._last_notified = None
            self._last_cover = None
            self._status = TB_PlayerStatus.CONNECTING
            self._start_uri(url)
        except Exception as e:
            self._last_error = str(e)
            self._status = TB_PlayerStatus.ERROR

    def load_playlist(
        self,
        filename: str | Path,
        autoplay: bool = True,
        startindex: int = 0,
        startposition: float | None = None,
    ) -> None:
        """Load an M3U or M3U8 playlist.

        Supported entries:
        - Absolute HTTP and HTTPS URLs
        - Absolute local file paths
        - Relative file paths resolved against the playlist directory
        - EXTINF titles used as fallback metadata

        Empty lines and comments are ignored.

        Args:
            filename: Path of the M3U/M3U8 file.
            autoplay: Start playback immediately.
            startindex: Index of the entry to start with. An index outside
                the playlist falls back to the first entry.
            startposition: Optional position in seconds within the start
                entry. It is applied once, when that entry is started (with
                ``autoplay=False`` on the next :meth:`play`). Values of 0 or
                less are ignored. If the source is not seekable, the entry
                simply starts from the beginning.
        """

        filename = os.path.expandvars(filename)
        path = Path(filename).expanduser().resolve()
        entries: list[dict[str, str]] = []
        pending_title = ""
        self._last_error = ""
        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                errors="replace",
            ) as file:
                for raw_line in file:
                    line = raw_line.strip()

                    if not line:
                        continue

                    if line.startswith("#EXTINF:"):
                        pending_title = line.split(",", 1)[-1].strip()
                        continue

                    if line.startswith("#"):
                        continue

                    parsed = urlparse(line)

                    if parsed.scheme:
                        uri = line
                    else:
                        uri = (path.parent / line).resolve().as_uri()

                    entries.append(
                        {
                            "uri": uri,
                            "title": pending_title,
                        }
                    )
                    pending_title = ""

            if not entries:
                raise ValueError(f"No playable entries found in {path}")

            self.stop()
            self._playlist = entries
            if startindex >= len(entries):
                self._index = 0
            else:
                self._index = startindex
            self._previous_index = -1
            self._mode = "playlist"
            self._url = None
            self._resume_position = float(startposition) if startposition is not None and startposition > 0 else None

            if autoplay:
                self.play()
        except Exception as e:
            self._last_error = str(e)
            self._status = TB_PlayerStatus.ERROR

    def play(self) -> None:
        """Start or resume playback of the current source.

        If a playlist is loaded, play the current playlist entry.
        After stop(), the current entry can be started again.
        """
        try:
            self._stopping = False
            self._cancel_reconnect()
            self._last_error = ""
            if self._mode == "playlist":
                if not self._playlist:
                    raise RuntimeError("No playlist has been loaded.")

                # Resume from the paused position instead of restarting the
                # entry. The real GStreamer state is checked as well, because
                # stop() can leave a late PAUSED bus message behind that sets
                # ``_status`` to PAUSED although the pipeline is already NULL.
                if self._status == TB_PlayerStatus.PAUSED and self._is_gst_paused():
                    result = self._player.set_state(Gst.State.PLAYING)
                    if result == Gst.StateChangeReturn.FAILURE:
                        self._status = TB_PlayerStatus.ERROR
                        self._schedule_reconnect()
                    return

                self._index = max(self._index, 0)

                self._play_playlist_index(self._index, self._resume_position)
                return

            if self._url is None:
                raise RuntimeError("No playback source has been configured.")

            self._status = TB_PlayerStatus.CONNECTING
            result = self._player.set_state(Gst.State.PLAYING)

            if result == Gst.StateChangeReturn.FAILURE:
                self._schedule_reconnect()
        except Exception as e:
            self._last_error = str(e)
            self._status = TB_PlayerStatus.ERROR

    def _is_gst_paused(self) -> bool:
        """Return whether the GStreamer pipeline is currently in PAUSED."""
        _, current_state, _ = self._player.get_state(0)
        return current_state == Gst.State.PAUSED

    def get_position(self) -> float | None:
        """Return the playback position in seconds.

        The position is available while playing or paused, also for a
        playlist entry that is paused. ``None`` is returned for radio
        streams, when nothing is loaded, or when the pipeline cannot answer
        the query yet (for example while connecting).
        """
        if self._mode == "radio":
            return None

        ok, position = self._player.query_position(Gst.Format.TIME)
        if not ok or position < 0:
            return None
        return position / Gst.SECOND

    def get_duration(self) -> float | None:
        """Return the duration of the current entry in seconds, if known."""
        if self._mode == "radio":
            return None

        ok, duration = self._player.query_duration(Gst.Format.TIME)
        if not ok or duration < 0:
            return None
        return duration / Gst.SECOND

    def pause(self) -> None:
        """Pause playback and update status when GStreamer confirms the state."""
        if self._status not in {
            TB_PlayerStatus.PLAYING,
            TB_PlayerStatus.BUFFERING,
            TB_PlayerStatus.CONNECTING,
        }:
            return

        result = self._player.set_state(Gst.State.PAUSED)
        if result == Gst.StateChangeReturn.FAILURE:
            self._status = TB_PlayerStatus.ERROR

    def stop(self) -> None:
        """Stop playback and cancel any pending reconnection.

        The loaded playlist is retained.
        """
        self._stopping = True
        self._cancel_reconnect()
        self._pending_seek = None
        self._player.set_state(Gst.State.NULL)
        self._status = TB_PlayerStatus.STOPPED
        self._last_notified = None

    def next(self) -> None:
        """Play the next playlist entry, wrapping at the end."""
        if not self._playlist:
            return

        self._previous_index = self._index
        self._index = (self._index + 1) % len(self._playlist)
        self._play_playlist_index(self._index)

    def previous(self) -> None:
        """Play the previous entry, wrapping at the beginning."""
        if not self._playlist:
            return

        if self._previous_index >= 0 and self._previous_index != self._index:
            target = self._previous_index
        else:
            target = (self._index - 1) % len(self._playlist)

        self._previous_index = self._index
        self._index = target
        self._play_playlist_index(self._index)

    def random(self) -> None:
        """Play a random playlist entry.

        Avoid selecting the current entry when multiple entries are available.
        """
        if not self._playlist:
            return

        candidates = list(range(len(self._playlist)))

        if len(candidates) > 1:
            candidates.remove(self._index)

        self._previous_index = self._index
        self._index = _random.choice(candidates)
        self._play_playlist_index(self._index)

    def _play_playlist_index(self, index: int, position: float | None = None) -> None:
        """Start the playlist entry at the specified index.

        Args:
            index: Playlist index to start.
            position: Optional start position in seconds within the entry.
        """
        entry = self._playlist[index]
        self._mode = "playlist"
        self._url = entry["uri"]
        # Any playlist start consumes the start position from load_playlist().
        self._resume_position = None
        self._pending_seek = position if position and position > 0 else None

        self._last_cover = None
        self._last_notified = None
        self._reconnect_attempt = 0
        self._stopping = False
        self._cancel_reconnect()
        self._status = TB_PlayerStatus.CONNECTING
        self._start_uri(entry["uri"])

    def _start_uri(self, source: str) -> None:
        """Reset the pipeline, configure the URI and start playback."""
        self._player.set_state(Gst.State.NULL)
        self._player.set_property("uri", self._to_uri(source))
        self._apply_volume()
        result = self._player.set_state(Gst.State.PLAYING)

        if result == Gst.StateChangeReturn.FAILURE:
            self._status = TB_PlayerStatus.ERROR
            self._schedule_reconnect()

    def _on_bus_message(self, bus: Any, message: Any) -> None:
        """Handle asynchronous GStreamer messages in the GLib context."""
        msg_type = message.type

        if msg_type == Gst.MessageType.TAG:
            tags = message.parse_tag()
            self._notify_metadata(tags)

        elif msg_type == Gst.MessageType.ERROR:
            error, _ = message.parse_error()

            self._last_error = f"{error.code}|{error.domain}: {error.message}"
            self._status = TB_PlayerStatus.ERROR
            if self._stopping or self._disposed:
                return

            if self._mode == "playlist":
                if len(self._playlist) > 1:
                    self.next()
                else:
                    self._schedule_reconnect()
            else:
                self._schedule_reconnect()

        elif msg_type == Gst.MessageType.EOS:
            if self._stopping or self._disposed:
                return

            if self._mode == "playlist":
                self.next()
            elif self._mode == "radio":
                self._schedule_reconnect()
            else:
                self._status = TB_PlayerStatus.STOPPED

        # disable buffering status while on a webstrem it toggles between buffering -> playing  ->buffering
        # elif msg_type == Gst.MessageType.BUFFERING:
        #     if self._stopping or self._disposed:
        #         return

        #     percent = message.parse_buffering()

        #     if percent < 100:
        #         if self._status != TT_PlayerStatus.BUFFERING:
        #             self._status_before_buffering = self._status
        #         self._status = TT_PlayerStatus.BUFFERING
        #     elif self._status == TT_PlayerStatus.BUFFERING:
        #         # Bei Streams endet das Puffern meist, bevor die Pipeline PLAYING
        #         # erreicht hat. PLAYING darf deshalb nur gesetzt werden, wenn die
        #         # Pipeline wirklich spielt; sonst würde die spätere Meldung
        #         # NULL/READY/PAUSED -> PLAYING die Statusmeldung verpassen könnte.
        #         _, current_state, _ = self._player.get_state(0)
        #         if current_state == Gst.State.PLAYING:
        #             self._status = TT_PlayerStatus.PLAYING
        #         else:
        #             self._status = self._status_before_buffering

        elif msg_type == Gst.MessageType.STATE_CHANGED:
            if message.src == self._player:
                old_state, new_state, pending_state = message.parse_state_changed()

                # Apply a requested start position once the pipeline has
                # prerolled (READY -> PAUSED). Seeking earlier fails, and
                # requiring old_state == READY ignores late PLAYING -> PAUSED
                # messages that a preceding stop() may still have queued.
                if self._pending_seek is not None and old_state == Gst.State.READY and new_state == Gst.State.PAUSED:
                    seek_seconds = self._pending_seek
                    self._pending_seek = None
                    self._player.seek_simple(
                        Gst.Format.TIME,
                        Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                        int(seek_seconds * Gst.SECOND),
                    )

                if new_state == Gst.State.PLAYING:
                    self._status = TB_PlayerStatus.PLAYING
                    self._reconnect_attempt = 0

                elif new_state == Gst.State.PAUSED:
                    # PAUSED with a pending state is only a stop-over: READY ->
                    # PAUSED (PLAYING pending) is the preroll while starting, and
                    # PLAYING -> PAUSED (READY pending) happens on the way to NULL
                    # in stop()/next(). Neither is a pause; reporting it would
                    # give a bogus PAUSED status.
                    if pending_state != Gst.State.VOID_PENDING:
                        return

                    self._status = TB_PlayerStatus.PAUSED

    def _notify_status_changed(self, old_status: TB_PlayerStatus) -> None:
        """Invoke the status callback if the visible status has changed."""
        new_status = self.status
        if self._status_callback is None or new_status == old_status:
            return

        try:
            self._status_callback(old_status, new_status)
        except Exception as exc:
            print(f"Status callback error ({old_status} -> {new_status}): {exc}")

    def _notify_metadata(self, tags: Any) -> None:
        """Invoke the metadata callback only when the metadata has changed."""
        if self._callback is not None:
            try:
                self._callback(tags)
            except Exception as exc:
                print(f"Metadata callback error: {exc}")

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnect using exponential backoff."""
        if self._stopping or self._disposed:
            return

        if self._reconnect_source is not None:
            return

        if self._reconnect_attempt >= self._max_reconnects:
            self._status = TB_PlayerStatus.ERROR
            return

        self._reconnect_attempt += 1
        self._status = TB_PlayerStatus.RECONNECTING

        self._reconnect_source = GLib.timeout_add_seconds(
            self._reconnect_delay,
            self._do_reconnect,
        )

    def _do_reconnect(self) -> bool:
        """Execute a scheduled reconnection attempt."""
        self._reconnect_source = None

        if self._stopping or self._disposed:
            return GLib.SOURCE_REMOVE

        if self._mode == "playlist":
            if self._index >= 0:
                self._play_playlist_index(self._index)

        elif self._url is not None:
            self._start_uri(self._url)

        return GLib.SOURCE_REMOVE

    def _cancel_reconnect(self) -> None:
        """Cancel a pending reconnection timer."""
        if self._reconnect_source is not None:
            GLib.source_remove(self._reconnect_source)
            self._reconnect_source = None

    def get_status(self) -> PlayerStatus:
        """Return a typed snapshot of the current player state and metadata."""
        _, current_state, _ = self._player.get_state(0)

        return PlayerStatus(
            status=self.status,
            mode=self._mode,
            url=self._url,
            playlist_index=self._index,
            playlist_length=len(self._playlist),
            volume=self._volume,
            volume_delta=self._volume_delta,
            muted=self._muted,
            reconnect_attempt=self._reconnect_attempt,
            gst_state=current_state.value_nick,
            playlist_song_position=self.get_position() or 0.0,
            playlist_song_duration=self.get_duration() or 0.0,
        )

    def close(self) -> None:
        """Release resources and prevent further playback operations."""
        if self._disposed:
            return
        self._stop_mainloop()
        self.stop()
        self._disposed = True

        bus = self._player.get_bus()
        if bus is None:
            raise RuntimeError("can't get audio-player bus")
        bus.remove_signal_watch()
        self._player.set_state(Gst.State.NULL)
