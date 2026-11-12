import asyncio
import io
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from urllib.request import urlopen

from PIL import Image, ImageFile

OnCoverCallback = Callable[[ImageFile.ImageFile], None]


class TB_CoverFetch:
    _logger = logging.getLogger(__name__)

    # Maximum number of concurrent / queued fetch jobs
    MAX_JOBS = 5

    def __init__(self, on_cover: OnCoverCallback) -> None:
        self.on_cover = on_cover

        # A plain thread pool works from any thread and needs no running event loop
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_JOBS, thread_name_prefix="cover-fetch")

        # Protects _active, which is accessed from the caller and the worker threads
        self._lock = threading.Lock()
        self._active: list[Future[None]] = []

    def _fetch_url(self, url: str) -> None:
        """Download an image, verify it and hand it to the on_cover callback.

        Runs in a worker thread (blocking I/O).
        """
        try:
            self._logger.debug(f"Fetch cover from {url}")

            # Open URL and read the response data
            with urlopen(url, timeout=10) as response:
                image_data = response.read()

            # Open image from bytes and check its integrity
            with Image.open(io.BytesIO(image_data)) as img:
                img.verify()

            # Reopen the image for processing, since verify() leaves the
            # image object in an unusable state
            with Image.open(io.BytesIO(image_data)) as img:
                self.on_cover(img)

        except Exception:
            self._logger.exception(f"Can't fetch image from {url}!")

    def fetch_location(self, location: str) -> Future[None]:
        """Fetch the favicon for the location URL from the webradio meta tag.

        Non-blocking: can be called from any thread. The returned future can
        be ignored (fire and forget), or waited for via future.result() in
        sync code or fetch_location_async() in async code.

        Args:
            location (str): location URL of the webradio

        Returns:
            Future[None]: future of the background job
        """
        url = f"https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url={location}&size=128"
        return self.fetch(url)

    def fetch(self, url: str) -> Future[None]:
        """Start fetching a cover image in the background (non-blocking).

        Args:
            url (str): image URL

        Returns:
            Future[None]: future of the background job
        """
        with self._lock:
            # If the job limit is reached, cancel and remove the oldest one.
            # Note: cancel() only works for jobs that are still queued,
            # a job that is already running cannot be stopped.
            if len(self._active) >= self.MAX_JOBS:
                self._active.pop(0).cancel()

            future = self._executor.submit(self._fetch_url, url)
            self._active.append(future)

        # Register the callback outside the lock: if the job is already done,
        # the callback runs immediately in this thread and would otherwise
        # try to acquire the (non-reentrant) lock a second time
        future.add_done_callback(self._on_done)
        return future

    async def fetch_async(self, url: str) -> None:
        """Awaitable variant of fetch() for async code."""
        await asyncio.wrap_future(self.fetch(url))

    async def fetch_location_async(self, location: str) -> None:
        """Awaitable variant of fetch_location() for async code."""
        await asyncio.wrap_future(self.fetch_location(location))

    def _on_done(self, future: Future[None]) -> None:
        """Remove a finished (or cancelled) job from the active list."""
        with self._lock:
            if future in self._active:
                self._active.remove(future)

    def close(self) -> None:
        """Shut down the thread pool without waiting for running jobs."""
        self._executor.shutdown(wait=False, cancel_futures=True)
