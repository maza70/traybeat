import os
import tempfile
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def user_temp_dir() -> Path:
    path = Path(tempfile.gettempdir(), f"{APP_ID}.{os.getuid()}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_version() -> str:
    try:
        return version("traybeat")
    except PackageNotFoundError:
        # src/traybeat/__init__.py -> project root is two levels up
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        try:
            with open(pyproject, "rb") as f:
                return tomllib.load(f)["project"]["version"]
        except (OSError, KeyError):
            return "unknown"


APP_ID = "de.maza.traybeat"
APP_NAME = "TrayBeat"
APP_DBUS_PATH = "/de/maza/traybeat"
APP_DBUS_PLAYER_SERVICE = "de.maza.traybeat.player"  # unique exportet name of the player interface do not change
APP_VERSION = _read_version()
ICON_NAME = "TrayBeat"
APP_ICON = "traybeat"
DESKTOP_ENTRY_NAME = "tray-beat"
CONFIG_PATH = Path(Path.home(), f".config/{APP_ID}")
TEMP_PATH = user_temp_dir()
STATE_PATH = Path(Path.home(), f".local/state/{APP_ID}")


"""The traybeat directory"""


# shutil.rmtree(TEMP_DIR, ignore_errors=True)
# TEMP_DIR.mkdir(parents=True, exist_ok=True)
