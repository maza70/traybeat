import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from typing import Any


class TB_Dispatch:
    _logger = logging.getLogger(__name__)

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()

        def run_async_loop() -> None:
            if self._loop is not None:
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()

        self._thread = threading.Thread(target=run_async_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        # close asyncio-Thread
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
            self._loop.close()
            self._loop = None

    def sub(self, coro: Coroutine[Any, Any, Any]) -> None:
        self.fnc(coro)

    def fnc(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future[Any]:

        if self._loop is None or not self._loop.is_running():
            self._logger.warning("Call without running event loop")
            coro.close()

            future: concurrent.futures.Future[Any] = concurrent.futures.Future()
            future.set_exception(RuntimeError("Event loop is not running"))
            return future

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def callback(f: concurrent.futures.Future[Any]):
            try:
                f.result()
            except Exception:
                self._logger.exception("Async task failed")

        future.add_done_callback(callback)
        return future
