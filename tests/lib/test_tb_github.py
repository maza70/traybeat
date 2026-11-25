import asyncio
from typing import Final
from unittest.mock import MagicMock, patch

import pytest

from traybeat.lib.tb_github import TB_Github, TB_Github_UpdateInfo

FAKE_NEWER: Final[dict[str, str]] = {
    "tag_name": "v1.0.0",
    "html_url": "https://example.com/release",
}
FAKE_SAME: Final[dict[str, str]] = {
    "tag_name": "v0.1.0",
    "html_url": "https://example.com/release",
}


# ----------------------------------------------------------------------
# check()
# ----------------------------------------------------------------------


async def test_check_newer_version() -> None:
    gh = TB_Github("0.1.0")

    with patch.object(gh, "_fetch_release", return_value=FAKE_NEWER):
        assert await gh.check() is True

    info = gh.get_info()
    assert info.check_successful is True
    assert info.update_available is True
    assert info.latest_version == "1.0.0"
    assert info.release_url == "https://example.com/release"


async def test_check_same_version() -> None:
    gh = TB_Github("0.1.0")

    with patch.object(gh, "_fetch_release", return_value=FAKE_SAME):
        assert await gh.check() is False

    info = gh.get_info()
    assert info.check_successful is True
    assert info.update_available is False


async def test_check_network_error() -> None:
    gh = TB_Github("0.1.0")

    with patch.object(gh, "_fetch_release", side_effect=OSError("offline")):
        assert await gh.check() is False

    assert gh.get_info().check_successful is False


async def test_check_invalid_response() -> None:
    gh = TB_Github("0.1.0")

    with patch.object(gh, "_fetch_release", return_value={"unexpected": "data"}):
        assert await gh.check() is False

    assert gh.get_info().check_successful is False


# ----------------------------------------------------------------------
# start() / automatische Prüfung
# ----------------------------------------------------------------------
async def test_callback_called_when_update_available() -> None:
    calls: list[TB_Github_UpdateInfo] = []
    gh = TB_Github("0.1.0", delay=0, on_update=calls.append)

    with patch.object(gh, "_fetch_release", return_value=FAKE_NEWER):
        gh.start()
        await gh.wait()

    assert len(calls) == 1
    assert calls[0].latest_version == "1.0.0"
    assert gh.running is False


async def test_async_callback() -> None:
    versions: list[str] = []

    async def on_update(info: TB_Github_UpdateInfo) -> None:
        if info.latest_version is not None:
            versions.append(info.latest_version)

    gh = TB_Github("0.1.0", delay=0, on_update=on_update)

    with patch.object(gh, "_fetch_release", return_value=FAKE_NEWER):
        gh.start()
        await gh.wait()

    assert versions == ["1.0.0"]


async def test_no_callback_when_up_to_date() -> None:
    calls: list[TB_Github_UpdateInfo] = []
    gh = TB_Github("0.1.0", delay=0, on_update=calls.append)

    with patch.object(gh, "_fetch_release", return_value=FAKE_SAME):
        gh.start()
        await gh.wait()

    assert calls == []
    assert gh.get_info().check_successful is True


async def test_retry_after_connection_error() -> None:
    calls: list[TB_Github_UpdateInfo] = []
    gh = TB_Github("0.1.0", delay=0, retry_delay=0.01, on_update=calls.append)

    mock_fetch: MagicMock
    with patch.object(gh, "_fetch_release", side_effect=[OSError("offline"), FAKE_NEWER]) as mock_fetch:
        gh.start()
        await gh.wait()

    assert mock_fetch.call_count == 2
    assert len(calls) == 1
    assert calls[0].latest_version == "1.0.0"


async def test_no_retry_after_successful_check() -> None:
    gh = TB_Github("0.1.0", delay=0, retry_delay=0.01)

    mock_fetch: MagicMock
    with patch.object(gh, "_fetch_release", return_value=FAKE_SAME) as mock_fetch:
        gh.start()
        await gh.wait()

    assert mock_fetch.call_count == 1


async def test_max_retries_gives_up() -> None:
    calls: list[TB_Github_UpdateInfo] = []
    gh = TB_Github(
        "0.1.0",
        delay=0,
        retry_delay=0.01,
        max_retries=2,
        on_update=calls.append,
    )

    mock_fetch: MagicMock
    with patch.object(gh, "_fetch_release", side_effect=OSError("offline")) as mock_fetch:
        gh.start()
        await gh.wait()

    # 1 erster Versuch + 2 Wiederholungen
    assert mock_fetch.call_count == 3
    assert calls == []
    assert gh.get_info().check_successful is False


async def test_callback_exception_does_not_crash_task() -> None:
    def broken_callback(info: TB_Github_UpdateInfo) -> None:
        raise RuntimeError("boom")

    gh = TB_Github("0.1.0", delay=0, on_update=broken_callback)

    with patch.object(gh, "_fetch_release", return_value=FAKE_NEWER):
        gh.start()
        await gh.wait()  # darf keine Exception werfen

    assert gh.running is False


async def test_stop_cancels_pending_check() -> None:
    calls: list[TB_Github_UpdateInfo] = []
    gh = TB_Github("0.1.0", delay=10, on_update=calls.append)

    mock_fetch: MagicMock
    with patch.object(gh, "_fetch_release", return_value=FAKE_NEWER) as mock_fetch:
        gh.start()
        assert gh.running is True

        await asyncio.sleep(0.05)
        await gh.stop()

    assert gh.running is False
    assert mock_fetch.call_count == 0
    assert calls == []


async def test_start_twice_creates_only_one_task() -> None:
    gh = TB_Github("0.1.0", delay=10)

    gh.start()
    assert gh.running is True
    gh.start()  # zweiter Aufruf darf nichts ändern
    assert gh.running is True

    await gh.stop()
    assert gh.running is False


async def test_wait_without_start_returns_immediately() -> None:
    gh = TB_Github("0.1.0", delay=10)

    await gh.wait()  # kein Task vorhanden, darf nicht blockieren

    assert gh.running is False


# ----------------------------------------------------------------------
# Optional: echter Netzwerktest (nicht bei jedem Lauf)
# ----------------------------------------------------------------------
@pytest.mark.network
async def test_check_real_api() -> None:
    gh = TB_Github("0.0.1")
    assert await gh.check() is True

    info = gh.get_info()
    assert info.check_successful is True
    assert info.update_available is True
