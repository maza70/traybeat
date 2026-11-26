import asyncio
import concurrent.futures
import functools
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")


class TB_Dispatch:
    _logger = logging.getLogger(__name__)

    def __init__(self) -> None:

        self._loop = asyncio.get_running_loop()

    def async_callback(
        self,
        callback: Callable[P, R | Awaitable[R]],
    ) -> Callable[P, R | None]:

        @functools.wraps(callback)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            result = callback(*args, **kwargs)

            if not inspect.isawaitable(result):
                return cast(R, result)

            loop = self._loop

            # Prüfen, ob der Event-Loop noch verfügbar ist.
            if loop.is_closed() or not loop.is_running():
                if inspect.iscoroutine(result):
                    result.close()

                self._logger.warning(
                    "Async callback %s ignored: event loop is not running",
                    callback.__qualname__,
                )
                return None

            async def await_result() -> R:
                return await cast(Awaitable[R], result)

            coro = await_result()

            try:
                future = asyncio.run_coroutine_threadsafe(coro, loop)
            except RuntimeError:
                # Der Event-Loop kann zwischen Prüfung und Einplanung
                # beendet worden sein.
                coro.close()

                if inspect.iscoroutine(result):
                    result.close()

                self._logger.warning(
                    "Could not schedule async callback %s: event loop stopped",
                    callback.__qualname__,
                    exc_info=True,
                )
                return None

            def handle_exception(
                future: concurrent.futures.Future[R],
            ) -> None:
                if future.cancelled():
                    return

                exception = future.exception()
                if exception is not None:
                    self._logger.error(
                        "Async callback %s failed",
                        callback.__qualname__,
                        exc_info=(
                            type(exception),
                            exception,
                            exception.__traceback__,
                        ),
                    )

            future.add_done_callback(handle_exception)
            return None

        return wrapper
