import importlib.resources
from pathlib import Path


class TB_Resource:
    @staticmethod
    def _get_resource(subfolder: str, filename: str):
        filename = filename.lstrip("/")
        subfolder = subfolder.lstrip("/")

        resource = importlib.resources.files("traybeat").joinpath("resources", subfolder, filename)

        if not resource.is_file():
            raise FileNotFoundError(f"Resource '{subfolder}/{filename}' not found.")

        return resource

    @staticmethod
    def get_bytes(subfolder: str, filename: str) -> bytes:
        return TB_Resource._get_resource(subfolder, filename).read_bytes()

    @staticmethod
    def get_path(subfolder: str, filename: str) -> Path:
        resource = TB_Resource._get_resource(subfolder, filename)

        return Path(str(resource))

    @staticmethod
    def get_folder(subfolder: str) -> Path:
        return Path(str(importlib.resources.files("traybeat").joinpath("resources", subfolder)))
