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
        #  self._loop: asyncio.AbstractEventLoop | None
        self._loop = asyncio.get_running_loop()

    # def start(self) -> None:
    #     self._loop = asyncio.new_event_loop()

    #     def run_async_loop() -> None:
    #         if self._loop is not None:
    #             asyncio.set_event_loop(self._loop)
    #             self._loop.run_forever()

    #     self._thread = threading.Thread(target=run_async_loop, daemon=True)
    #     self._thread.start()

    # def stop(self) -> None:
    #     # close asyncio-Thread
    #     if self._loop is not None:
    #         self._loop.call_soon_threadsafe(self._loop.stop)
    #         self._thread.join()
    #         self._loop.close()
    #         self._loop = None

    def async_callback(
        self,
        callback: Callable[P, R | Awaitable[R]],
    ) -> Callable[P, R | None]:

        @functools.wraps(callback)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            result = callback(*args, **kwargs)

            if inspect.isawaitable(result):
                loop = self._loop

                if not loop.is_running():
                    raise RuntimeError("Asyncio event loop is not running")

                async def await_result() -> R:
                    return await cast(Awaitable[R], result)

                future = asyncio.run_coroutine_threadsafe(
                    await_result(),
                    loop,
                )

                def handle_exception(future: concurrent.futures.Future[R]) -> None:
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

            return cast(R, result)

        return wrapper

    # def sub(self, coro: Coroutine[Any, Any, Any]) -> None:
    #     self.fnc(coro)

    # def fnc(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future[Any]:

    #     if self._loop is None or not self._loop.is_running():
    #         self._logger.warning("Call without running event loop")
    #         coro.close()

    #         future: concurrent.futures.Future[Any] = concurrent.futures.Future()
    #         future.set_exception(RuntimeError("Event loop is not running"))
    #         return future

    #     future = asyncio.run_coroutine_threadsafe(coro, self._loop)

    #     def callback(f: concurrent.futures.Future[Any]):
    #         try:
    #             f.result()
    #         except Exception:
    #             self._logger.exception("Async task failed")

    #     future.add_done_callback(callback)
    #     return future
