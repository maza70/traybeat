import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version


@dataclass
class TB_Github_UpdateInfo:
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
    check_successful: bool = False


import inspect
import logging
from collections.abc import Awaitable, Callable

UpdateCallback = Callable[[TB_Github_UpdateInfo], Awaitable[None] | None]


class TB_Github:
    """Check GitHub once after a delay for a newer stable release."""

    _logger = logging.getLogger(__name__)

    def __init__(
        self,
        current_version: str,
        owner: str = "maza70",
        repo: str = "traybeat",
        delay: float = 30 * 60,
        retry_delay: float = 30 * 60,
        max_retries: int | None = None,
        on_update: UpdateCallback | None = None,
    ):
        """
        :param delay: Sekunden zwischen start() und der ersten Prüfung.
        :param retry_delay: Sekunden bis zum nächsten Versuch, wenn keine Verbindung möglich war.
        :param max_retries: Maximale Anzahl Wiederholungen (None = unbegrenzt).
        :param on_update: Callback (sync oder async), wird nur bei verfügbarem Update aufgerufen.
        """
        self.info = TB_Github_UpdateInfo(current_version=current_version)
        self.owner = owner
        self.repo = repo
        self.delay = delay
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.on_update = on_update
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Einmalige Prüfung
    # ------------------------------------------------------------------
    def _fetch_release(self) -> dict[str, Any]:
        """Blocking HTTP request (runs in a worker thread)."""
        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"
        request = Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Python-Update-Checker",
            },
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    async def wait(self) -> None:
        """Wait until the scheduled check has finished."""
        if self._task is not None:
            await self._task

    async def check(self) -> bool:
        """Check asynchronously whether a newer release is available."""
        try:
            release = await asyncio.to_thread(self._fetch_release)

            latest = release["tag_name"].lstrip("v")

            current_version = Version(self.info.current_version)
            latest_version = Version(latest)

            self.info.latest_version = latest
            self.info.release_url = release["html_url"]
            self.info.update_available = latest_version != current_version
            self.info.check_successful = True

            return self.info.update_available

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            InvalidVersion,
        ):
            self.info.check_successful = False
            return False

    # ------------------------------------------------------------------
    # Verzögerte, einmalige Prüfung mit Wiederholung bei Verbindungsfehler
    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        """True, solange noch gewartet oder geprüft wird."""
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Schedule the check in the background (needs a running event loop)."""

        if self.running:
            return
        self._task = asyncio.create_task(self._run(), name="tb_github_update_checker")

    async def stop(self) -> None:
        """Cancel a pending check."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        self._logger.info(f"start update chack in {self.delay} seconds.")
        await asyncio.sleep(self.delay)

        retries = 0
        while True:
            try:
                update_available = await self.check()

                if self.info.check_successful:
                    # Verbindung hat geklappt: einmal melden (falls Update) und fertig.
                    if update_available:
                        await self._notify()
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Update check failed unexpectedly")
                return

            # Keine Verbindung -> später erneut versuchen.
            if self.max_retries is not None and retries >= self.max_retries:
                self._logger.info("Update check given up after %d retries", retries)
                return
            retries += 1
            await asyncio.sleep(self.retry_delay)

    async def _notify(self) -> None:
        if self.on_update is None:
            return
        try:
            result = self.on_update(self.info)
            if inspect.isawaitable(result):
                await result
        except Exception:
            self._logger.exception("Update callback raised an exception")

    def get_info(self) -> TB_Github_UpdateInfo:
        """Return update information as a dataclass."""
        return self.info
