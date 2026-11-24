import re
import tomllib
from pathlib import Path

from pyconjury.models.errors import PyConjuryError
from pyconjury.models.github_storage import GitHubLocalStorage
from pyconjury.models.links import GithubPackageURL, PackageLink
from pyconjury.models.package_skills import PackageSkills
from pyconjury.models.storage import PyconjuryStorage


def _agents_skills_folder() -> Path:
    return Path.home() / ".agents" / "skills"


def _matches_package_source(target: str, package_link: PackageLink) -> bool:
    if isinstance(package_link, GithubPackageURL):
        return target == package_link.url
    return Path(target).expanduser().resolve() == package_link.path.expanduser().resolve()


def _normalize_package_name(package_name: str) -> str:
    return re.sub(r"[-_.]+", "-", package_name).casefold()


def _package_folder_for(storage: PyconjuryStorage, package: PackageSkills) -> Path:
    if isinstance(package.package_link, GithubPackageURL):
        return GitHubLocalStorage.package_folder(storage.github_folder, package.package_link.url)
    return package.package_link.path


def _read_package_name(package_folder: Path) -> str:
    pyproject_path = package_folder / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as pyproject_file:
            metadata = tomllib.load(pyproject_file)
    except OSError as error:
        raise PyConjuryError(f"Cannot read Python project metadata {pyproject_path}: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise PyConjuryError(f"Invalid Python project metadata {pyproject_path}: {error}") from error

    project = metadata.get("project")
    package_name = project.get("name") if isinstance(project, dict) else None
    if not isinstance(package_name, str) or not package_name.strip():
        raise PyConjuryError(f"Python project must declare a non-empty [project].name in {pyproject_path}.")
    return package_name.strip()
