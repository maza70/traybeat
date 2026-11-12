import argparse
import fcntl
import logging
import os
import sys
import types
from pathlib import Path

from traybeat.core.core import Core
from traybeat.core.tb_config import TB_StartupConfig
from traybeat.lib.tb_const import APP_NAME, APP_VERSION, TEMP_PATH


def acquire_single_instance_lock():
    lock_path = Path(TEMP_PATH, "traybeat.lock")
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None

    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.description = f"TrayBeat {APP_VERSION}:\nA small system tray controled webradio and m3u playlist player."
    parser.epilog = "Copyright (C) 2026 Matthias Zartmann <mail-traybeat@ma-za.de>"
    parser.prog = APP_NAME

    parser.add_argument(
        "-l",
        "--logfile",
        help="Instead of logging to the console, log is written to this file.",
    )
    parser.add_argument(
        "-t",
        "--tracelevel",
        choices=["DEBUG", "INFO", "WARN", "ERROR", "FATAL"],
        default="INFO",
        help="Set tracelevel (Standard: %(default)s).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Internal webserver port (Standard: %(default)s = choose a free port).",
    )

    parser.add_argument(
        "--bind",
        type=str,
        default="localhost",
        help="Internal webserver binding address (Standard: %(default)s).",
    )
    parser.add_argument(
        "--ws_port",
        type=int,
        default=0,
        help="Internal websocket port (Standard: %(default)s = choose a free port).",
    )

    parser.add_argument(
        "--ws_bind",
        type=str,
        default="localhost",
        help="Internal websocket server binding address (Standard: %(default)s).",
    )
    parser.add_argument(
        "--icon_theme",
        type=str,
        choices=["dark", "light"],
        default="dark",
        help="Set icon theme (Standard: %(default)s).",
    )

    parser.add_argument("-p", "--play", action="store_true", help="Automatically plays the last station played.")
    args = parser.parse_args()
    startupConfig = TB_StartupConfig()
    if args.logfile is not None:
        startupConfig.logFile = Path(str(args.logfile).strip()).expanduser().absolute()
    if args.play == True:
        startupConfig.play = True
    if args.tracelevel is not None:
        startupConfig.traceLevel = args.tracelevel
    if args.port is not None:
        startupConfig.webserver_port = args.port
    if args.bind is not None:
        startupConfig.webserver_bind = args.bind
    if args.ws_port is not None:
        startupConfig.websocket_port = args.ws_port
    if args.ws_bind is not None:
        startupConfig.websocket_bind = args.ws_bind

    if args.icon_theme is not None:
        startupConfig.icon_theme = args.icon_theme

    lock = acquire_single_instance_lock()
    if lock is None:
        print("TrayBeat is already running. Please close the other instance before starting it again.", file=sys.stderr)
        sys.exit(1)
    is_kde = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")
    if not is_kde:
        print("TrayBeat runs only under KDE desktop environment!")

    tray_beat_player = Core(startupConfig)
    tray_beat_player.start()
    sys.exit(0)


# Nicht abgefangene Exceptions zentral protokollieren
def handle_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: types.TracebackType | None,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.getLogger("uncaught").critical(
        "Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


if __name__ == "__main__":
    sys.excepthook = handle_exception
    main()
