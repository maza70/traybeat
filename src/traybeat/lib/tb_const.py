import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from platformdirs import user_cache_path, user_config_path, user_state_path


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
APP_NAME = "traybeat"
APP_DBUS_PATH = "/de/maza/traybeat"
APP_DBUS_PLAYER_SERVICE = "de.maza.traybeat.player"  # unique exportet name of the player interface do not change
APP_VERSION = _read_version()
ICON_NAME = "TrayBeat"
APP_ICON = "de.maza.traybeat"
DESKTOP_ENTRY_NAME = "tray-beat"
CONFIG_PATH = user_config_path(APP_ID)
TEMP_PATH = user_cache_path(APP_ID)
STATE_PATH = user_state_path(APP_ID)

Path.mkdir(CONFIG_PATH, exist_ok=True)
Path.mkdir(TEMP_PATH, exist_ok=True)
Path.mkdir(STATE_PATH, exist_ok=True)


"""The traybeat directory"""


# shutil.rmtree(TEMP_DIR, ignore_errors=True)
# TEMP_DIR.mkdir(parents=True, exist_ok=True)
