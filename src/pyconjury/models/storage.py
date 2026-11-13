import os
import sys
from pathlib import Path
from typing import Self, Sequence

from .errors import PyConjuryError
from .github_storage import GitHubLocalStorage
from .package_skills import PackageSkills


class PyconjuryStorage:
    def __init__(self, root_folder: Path) -> None:
        self.root_folder = root_folder.expanduser().resolve()

        self.packages_by_name = {
            path.stem: PackageSkills.from_toml_file(path) for path in self.root_folder.glob("*.toml")
        }

    @classmethod
    def from_storage_folder(cls, root_folder: Path | None = None) -> Self:
        if root_folder is None:
            configured_root = os.environ.get("PYCONJURY_HOME", os.environ.get("MYSKILL_HOME"))
            root_folder = Path(configured_root).expanduser() if configured_root else cls._default_storage_folder()
        return cls(root_folder=root_folder)

    @staticmethod
    def _default_storage_folder() -> Path:
        if sys.platform == "win32":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                return Path(local_app_data) / "myskill"
            raise PyConjuryError("LOCALAPPDATA is not set; configure PYCONJURY_HOME to choose a storage folder.")

        if sys.platform.startswith("linux"):
            xdg_data_home = os.environ.get("XDG_DATA_HOME")
            if xdg_data_home:
                xdg_data_path = Path(xdg_data_home).expanduser()
                if xdg_data_path.is_absolute():
                    return xdg_data_path / "myskill"
            return Path.home() / ".local" / "share" / "myskill"

        raise PyConjuryError(f"Unsupported operating system: {sys.platform}. pyconjury supports Windows and Linux.")

    @property
    def github_folder(self) -> Path:
        return self.root_folder / "github"

    @property
    def all_packages(self) -> Sequence[PackageSkills]:
        return list(self.packages_by_name.values())

    @property
    def package_names(self) -> Sequence[str]:
        return list(self.packages_by_name.keys())

    def get_package_skills(self, package_name: str) -> PackageSkills:
        return self.packages_by_name[package_name]

    @property
    def github_storage(self) -> GitHubLocalStorage:
        return GitHubLocalStorage(root_folder=self.github_folder)
