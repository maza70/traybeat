import os
import shutil
import subprocess
import sys
from pathlib import Path

from traybeat.lib.tb_const import APP_ID


class TB_AppImage:
    def __init__(
        self,
        app_id: str = APP_ID,
        desktop_filename: str = f"{APP_ID}.desktop",
        icon_filename: str = f"{APP_ID}.svg",
    ):
        self.app_id = app_id

        self.appdir = Path(os.environ.get("APPDIR", ""))
        self.appimage = Path(os.environ.get("APPIMAGE", ""))

        self.source_desktop = self.appdir / desktop_filename
        self.source_icon = self.appdir / icon_filename

        self.data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))

        self.desktop_dir = self.data_home / "applications"
        self.icon_dir = self.data_home / "icons/hicolor/scalable/apps"

        self.target_desktop = self.desktop_dir / desktop_filename
        self.target_icon = self.icon_dir / icon_filename

    @staticmethod
    def _desktop_quote(value: str):
        """Escape a value for use as a Desktop Entry Exec argument."""
        value = str(value)
        value = value.replace("\\", "\\\\")
        value = value.replace('"', '\\"')
        value = value.replace("`", "\\`")
        value = value.replace("$", "\\$")
        return f'"{value}"'

    @staticmethod
    def _update_desktop_database(directory: str):
        """Refresh the desktop application database if available."""
        command = shutil.which("update-desktop-database")

        if command:
            subprocess.run(
                [command, directory],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

    def _is_run_in_appimage(self) -> bool:
        return os.environ.get("APPIMAGE") is not None

    def _exit(self, errormsg: str) -> bool:
        print(errormsg, file=sys.stderr)
        sys.exit(1)

    def install(self):
        if not self._is_run_in_appimage():
            self._exit("Not running as an AppImage. Installation aborted.")
        print(" Install the desktop entry and icon for the current user")
        print("-=======================================================-\n")

        if not self.appimage.is_file():
            self._exit("APPIMAGE is not set or does not exist.")

        if not self.source_desktop.is_file():
            self._exit(f"Desktop file not found: {self.source_desktop}")

        if not self.source_icon.is_file():
            self._exit(f"Icon file not found: {self.source_icon}")

        self.desktop_dir.mkdir(parents=True, exist_ok=True)
        self.icon_dir.mkdir(parents=True, exist_ok=True)

        desktop_content = self.source_desktop.read_text(encoding="utf-8")
        exec_line = f"Exec={self._desktop_quote(str(self.appimage.resolve()))} %U"
        lines = desktop_content.splitlines()
        exec_found = False

        for index, line in enumerate(lines):
            if line.startswith("Exec="):
                lines[index] = exec_line
                exec_found = True
                break

        if not exec_found:
            self._exit("Desktop file does not contain an Exec entry.")

        temporary_desktop = self.target_desktop.with_suffix(".desktop.tmp")
        temporary_desktop.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print(f"Install: {self.target_desktop}")
        os.replace(temporary_desktop, self.target_desktop)
        print(f"Install: {self.target_icon}")
        shutil.copy2(self.source_icon, self.target_icon)

        self._update_desktop_database(str(self.desktop_dir))

        return True

    def uninstall(self):
        """Remove the desktop entry and icon for the current user."""
        if not self._is_run_in_appimage():
            self._exit("Not running as an AppImage. Uninstallation aborted.")

        print(" Uninstall the desktop entry and icon for the current user.")
        print("-==========================================================- \n")
        print("If you have any suggestions for improvement, I'd appreciate your feedback. Feel free to let me know what I could do better.")
        print("Email: mail@ma-za.de")
        print("GitHub issue: https://github.com/maza70/traybeat/issues\n")

        removed = False

        for path in (self.target_desktop, self.target_icon):
            try:
                if not path.is_file():
                    print(f"File {path} not found.")
                else:
                    print(f"Remove {path}.")
                    path.unlink()

                removed = True
            except FileNotFoundError:
                pass

        self._update_desktop_database(str(self.desktop_dir))

        return removed
