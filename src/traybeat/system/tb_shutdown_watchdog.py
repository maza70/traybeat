"""Detect system shutdown, reboot and session end and offer a save callback.

The callback is triggered at most once, by whichever source reports first:

1. systemd-logind (system bus): ``PrepareForShutdown(true)`` announces a
   shutdown or reboot. While the watchdog runs it holds a *delay* inhibitor
   lock, so logind waits with the actual shutdown until the callback has
   finished (limited by ``InhibitDelayMaxSec`` in ``logind.conf``, 5 s by
   default).
2. Termination signals (``SIGTERM``, ``SIGHUP``, ``SIGINT``, ``SIGQUIT`` and,
   on Linux, ``SIGPWR``): KDE normally ends the user session first and only
   asks logind to power off afterwards, so the application may be terminated
   before logind announces anything. Applications that are stopped this way
   receive ``SIGTERM``. ``SIGINT`` is what Ctrl+C sends, ``SIGQUIT`` what
   Ctrl+\\ sends.

Requires ``dbus_next`` and an asyncio event loop. Signals are handled by that
loop if it runs in the main thread. If the asyncio loop runs in a background
thread next to a ``GLib.MainLoop`` in the main thread, ``start()`` schedules
GLib signal registration on the main GLib context automatically. Start the
GLib main loop after ``start()`` has completed.

Example:
    >>> async def main() -> None:
    ...     watchdog = TT_ShutdownWatchdog(save_state)
    ...     await watchdog.start()
    ...     await asyncio.Event().wait()
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import signal
import threading
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import BusType

log = logging.getLogger(__name__)

LOGIND_NAME = "org.freedesktop.login1"
LOGIND_PATH = "/org/freedesktop/login1"
LOGIND_MANAGER = "org.freedesktop.login1.Manager"

# Signals that ask the process to end. SIGQUIT is sent by Ctrl+\, SIGPWR
# (Linux only) announces a power failure. Left out on purpose: SIGUSR1/SIGUSR2
# and the timer signals (application use), SIGPIPE (Python ignores it) and
# fault signals like SIGSEGV or SIGABRT (not safely handled in Python), as well
# as SIGKILL/SIGSTOP, which cannot be caught at all.
_SHUTDOWN_SIGNALS: tuple[signal.Signals, ...] = tuple(
    getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT", "SIGPWR") if hasattr(signal, name)
)

# GLib.unix_signal_add() only supports SIGHUP, SIGINT, SIGTERM, SIGUSR1,
# SIGUSR2 and SIGWINCH; the other termination signals need a Python handler.
_GLIB_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

# Handlers that mean "the application has not set up its own handling".
# Python installs default_int_handler for SIGINT, SIG_DFL for the others.
_DEFAULT_HANDLERS = (signal.SIG_DFL, signal.default_int_handler)


def _is_default_handler(handler: Any) -> bool:
    """Return whether a signal handler is a default, not an application one."""
    if handler in _DEFAULT_HANDLERS:
        return True
    # asyncio.run() (Python 3.11+) installs its own SIGINT handler, a partial
    # of Runner._on_sigint. It only cancels the main task, so it counts as
    # a default handler too.
    owner = getattr(getattr(handler, "func", None), "__self__", None)
    return type(owner).__name__ == "Runner"


ShutdownCallback = Callable[[str], Awaitable[None] | None]


class TB_ShutdownWatchdog:
    """Call a save callback when the system shuts down or the session ends.

    The callback receives a reason string: ``"shutdown"`` (logind, covers
    shutdown and reboot) or ``"signal:<NAME>"`` for a termination signal,
    for example ``"signal:SIGTERM"`` or ``"signal:SIGINT"`` (Ctrl+C), see
    ``_SHUTDOWN_SIGNALS``. It may be a plain function or a coroutine
    function and runs in the event-loop thread, so keep it short; blocking
    calls block the loop. Exceptions are logged and never prevent the
    shutdown.

    Args:
        on_shutdown: Callback invoked with the reason string.
        who: Name shown by logind for the inhibitor lock.
        why: Reason shown by logind for the inhibitor lock.
        handle_signals: Also react to the termination signals (SIGINT,
            SIGTERM, SIGHUP, SIGQUIT and on Linux SIGPWR).
            If the asyncio loop runs in the main thread, signals are registered
            with asyncio. If it runs in a background thread, GLib signal
            registration is scheduled on the main GLib context.
            A signal is only taken over if the application has not installed
            its own handler; in that case call :meth:`fire` from your
            handler instead.
        exit_on_signal: After the callback ran because of a signal, deliver
            the signal again with its default action so the process ends as
            it would have without the watchdog (for Ctrl+C that is a
            ``KeyboardInterrupt``). Set to ``False`` if the application
            quits on its own after the callback.
    """

    def __init__(
        self,
        on_shutdown: ShutdownCallback,
        *,
        who: str = "ktraytune",
        why: str = "Saving data before shutdown",
        handle_signals: bool = True,
        exit_on_signal: bool = True,
    ) -> None:
        self._on_shutdown = on_shutdown
        self._who = who
        self._why = why
        self._handle_signals = handle_signals
        self._exit_on_signal = exit_on_signal

        self._started = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._manager: Any = None
        self._lock_fd: int | None = None
        self._fired = False
        self._signals: list[signal.Signals] = []
        self._glib_signals_attached = False
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Connect to logind, take the inhibitor lock and hook signals.

        If logind is not reachable, a warning is logged and only the signal
        handling stays active.
        """
        if self._started:
            return
        self._started = True
        self._loop = asyncio.get_running_loop()

        await self._connect_logind()
        if self._handle_signals:
            self._install_signal_handlers()

    def stop(self) -> None:
        """Release the lock, remove signal handlers and disconnect."""
        self._remove_signal_handlers()
        self._release_lock()
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
        self._manager = None
        self._started = False

    def attach_glib_signals(
        self,
        on_done: Callable[[], None] | None = None,
        timeout: float = 5.0,
    ) -> None:
        """Handle the termination signals through the GLib main loop.

        For applications with a ``GLib.MainLoop`` in the main thread and the
        asyncio loop (and this watchdog) in a background thread. Python signal
        handlers only run in the main thread, so the signals are taken over
        here. SIGINT, SIGTERM and SIGHUP go through GLib, the only ones GLib
        supports. The others (SIGQUIT, SIGPWR) use a Python signal handler,
        which the GLib main loop of PyGObject runs in the main thread as well.

        Call it from the main thread after :meth:`start` has finished. When a
        signal arrives, the callback runs in the asyncio thread; the main
        thread waits for it (up to ``timeout`` seconds) and then calls
        ``on_done``, for example ``main_loop.quit``. SIGINT, SIGTERM and
        SIGHUP are handled once, a second one gets its default action again
        (a hard exit if the application hangs). Signals with an application
        handler of its own are left alone.

        Args:
            on_done: Called in the main thread after the callback finished.
            timeout: Seconds to wait for the callback before calling on_done.
        """
        if self._glib_signals_attached:
            return

        from gi.repository import GLib  # type: ignore

        for sig in _SHUTDOWN_SIGNALS:
            if sig in _GLIB_SIGNALS:
                GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self._on_glib_signal, sig, on_done, timeout)
            elif _is_default_handler(signal.getsignal(sig)):
                signal.signal(
                    sig,
                    lambda signum, _frame: self._on_glib_signal(signum, on_done, timeout),
                )

        self._glib_signals_attached = True

    async def fire(self, reason: str) -> None:
        """Run the callback once and release the inhibitor lock afterwards.

        Called internally on shutdown or signal; applications with their own
        signal handlers can call it directly. Further calls are ignored until
        a cancelled shutdown re-arms the watchdog.
        """
        if self._fired:
            return
        self._fired = True

        try:
            result = self._on_shutdown(reason)
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception("Shutdown callback failed (reason: %s)", reason)
        finally:
            self._release_lock()

    # -- logind -----------------------------------------------------------

    async def _connect_logind(self) -> None:
        bus: MessageBus | None = None
        try:
            bus = await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=True).connect()
            introspection = await bus.introspect(LOGIND_NAME, LOGIND_PATH)
            proxy = bus.get_proxy_object(LOGIND_NAME, LOGIND_PATH, introspection)
            manager: Any = proxy.get_interface(LOGIND_MANAGER)
            manager.on_prepare_for_shutdown(self._on_prepare_for_shutdown)
        except Exception:
            log.warning("systemd-logind is not available", exc_info=True)
            if bus is not None:
                bus.disconnect()
            return

        self._bus = bus
        self._manager = manager
        await self._take_lock()

    def _on_prepare_for_shutdown(self, active: bool) -> None:
        if active:
            self._spawn(self.fire("shutdown"))
        else:
            # The shutdown was cancelled: re-arm and take the lock again.
            self._fired = False
            self._spawn(self._take_lock())

    async def _take_lock(self) -> None:
        if self._manager is None or self._lock_fd is not None:
            return
        try:
            self._lock_fd = await self._manager.call_inhibit("shutdown", self._who, self._why, "delay")
        except Exception:
            log.warning("Could not take the shutdown inhibitor lock", exc_info=True)

    def _release_lock(self) -> None:
        if self._lock_fd is None:
            return
        try:
            os.close(self._lock_fd)
        except OSError:
            pass
        self._lock_fd = None

    # -- signals ----------------------------------------------------------

    def _on_glib_signal(self, sig: int, on_done: Callable[[], None] | None, timeout: float) -> bool:
        name = signal.Signals(sig).name
        loop = self._loop
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.fire(f"signal:{name}"), loop)
            try:
                future.result(timeout=timeout)
            except Exception:
                log.exception("Shutdown callback failed (signal %s)", name)
        if on_done is not None:
            on_done()
        return False  # remove this source; a repeated signal gets its default

    def _install_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            # The asyncio loop is in a worker thread, while GLib's main loop
            # runs in the main thread. Queue signal registration onto GLib's
            # default main context; it will run once that main loop starts.
            try:
                from gi.repository import GLib  # type: ignore

                GLib.idle_add(self._attach_glib_signals_from_main_thread)
                log.debug("Scheduled GLib signal registration on the main thread")
            except Exception:
                log.exception("Could not schedule GLib signal registration")
            return

        loop = asyncio.get_running_loop()
        for sig in _SHUTDOWN_SIGNALS:
            if not _is_default_handler(signal.getsignal(sig)):
                continue  # the application handles this signal itself
            try:
                loop.add_signal_handler(sig, self._on_signal, sig)
            except (NotImplementedError, RuntimeError, ValueError):
                log.warning("Cannot handle %s outside the main thread", sig.name)
                continue
            self._signals.append(sig)

    def _attach_glib_signals_from_main_thread(self) -> bool:
        """GLib idle callback: attach signal handlers from the main thread."""
        try:
            self.attach_glib_signals()
        except Exception:
            log.exception("Could not attach GLib signal handlers")
        return False  # run this idle callback only once

    def _remove_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for sig in self._signals:
            loop.remove_signal_handler(sig)
        self._signals.clear()

    def _on_signal(self, sig: signal.Signals) -> None:
        self._spawn(self._handle_signal(sig))

    async def _handle_signal(self, sig: signal.Signals) -> None:
        await self.fire(f"signal:{sig.name}")
        if self._exit_on_signal:
            # Removing the handler restores the default action; delivering
            # the signal again ends the process as it would have before.
            # Sent from a loop callback instead of the task, so Ctrl+C ends
            # the program with a plain KeyboardInterrupt and no task warning.
            # SIGQUIT would end with a core dump by default, so it is turned
            # into SIGTERM for a clean exit.
            exit_signal = signal.SIGTERM if sig == signal.SIGQUIT else sig
            self._remove_signal_handlers()
            asyncio.get_running_loop().call_soon(os.kill, os.getpid(), exit_signal)

    # -- helpers ----------------------------------------------------------

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
