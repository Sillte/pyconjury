import re
import subprocess
import tomllib
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit

from pyconjury.infra.filesystem_link_creator import create_default_file_system_link_creator
from pyconjury.models.errors import PyConjuryError
from pyconjury.models.links import GithubPackageURL, LocalPackagePath, PackageLink, SkillPath
from pyconjury.models.package_skills import PackageSkills
from pyconjury.models.storage import PyconjuryStorage
from pyconjury.skill_searcher import SkillSearcher


class ConjuryInstallerService:
    def list_packages(self) -> Sequence[tuple[str, PackageSkills]]:
        storage = PyconjuryStorage.from_storage_folder()
        packages: list[tuple[str, PackageSkills]] = []
        for package_key in storage.package_names:
            package = storage.get_package_skills(package_key)
            package_name = package.package_name or _read_package_name(
                _package_folder_for(storage, package_key, package)
            )
            packages.append((package_name, package))
        return sorted(packages, key=lambda entry: _normalize_package_name(entry[0]))

    def list_skills(self, package_name: str) -> Sequence[SkillPath]:
        packages = [
            package
            for registered_name, package in self.list_packages()
            if _normalize_package_name(registered_name) == _normalize_package_name(package_name)
        ]
        if not packages:
            raise PyConjuryError(f"No installed package matches {package_name!r}.")
        return sorted(
            (skill_path for package in packages for skill_path in package.skill_paths),
            key=lambda skill_path: skill_path.skill_name.casefold(),
        )

    def install(self, source: str | Path) -> PackageSkills:
        if isinstance(source, Path):
            return self.install_local(source)
        if _is_github_source(source):
            return self.install_github(source)
        return self.install_local(Path(source))

    def install_github(self, url: str) -> PackageSkills:
        storage = PyconjuryStorage.from_storage_folder()
        repository_folder = storage.github_storage.fetch(url, update=True)
        return self._install_package(storage, repository_folder, GithubPackageURL(url=url), url)

    def install_local(self, path: Path) -> PackageSkills:
        package_folder = path.expanduser().resolve()
        if not package_folder.is_dir():
            raise PyConjuryError(f"Local Python project directory does not exist: {package_folder}")
        if not (package_folder / "pyproject.toml").is_file():
            raise PyConjuryError(f"Local path is not a Python project with pyproject.toml: {package_folder}")
        storage = PyconjuryStorage.from_storage_folder()
        return self._install_package(storage, package_folder, LocalPackagePath(path=package_folder), package_folder)

    def uninstall(self, target: str) -> tuple[bool, Sequence[str]]:
        storage = PyconjuryStorage.from_storage_folder()
        packages = [(name, storage.get_package_skills(name)) for name in storage.package_names]
        source_matches = [entry for entry in packages if _matches_package_source(target, entry[1].package_link)]
        if len(source_matches) > 1:
            raise PyConjuryError(f"Multiple installed packages match {target!r}; uninstall by package name instead.")

        if source_matches:
            selected_packages = source_matches
        else:
            selected_packages = []
            for name, package in packages:
                registered_name = package.package_name or _read_package_name(
                    _package_folder_for(storage, name, package)
                )
                if _normalize_package_name(registered_name) == _normalize_package_name(target):
                    selected_packages.append((name, package))

        if not selected_packages:
            raise PyConjuryError(f"No installed package matches {target!r}.")

        removed_skill_names = sorted(
            (
                skill_path.skill_name
                for _, package in selected_packages
                for skill_path in package.skill_paths
            ),
            key=str.casefold,
        )

        package_names = {
            _read_package_name(_package_folder_for(storage, name, package))
            if package.package_name is None
            else package.package_name
            for name, package in selected_packages
        }
        normalized_package_names = {_normalize_package_name(name) for name in package_names}
        if len(normalized_package_names) != 1:
            raise PyConjuryError(f"The selected registrations use different Python package names: {target!r}.")
        package_name = next(iter(package_names))
        selected_keys = {name for name, _ in selected_packages}
        shared_package = False
        for name, package in packages:
            if name in selected_keys:
                continue
            other_package_name = package.package_name or _read_package_name(_package_folder_for(storage, name, package))
            if _normalize_package_name(other_package_name) in normalized_package_names:
                shared_package = True
                break

        link_creator = create_default_file_system_link_creator()
        skills_folder = _agents_skills_folder()
        links = [
            (
                _package_folder_for(storage, package_key, package) / skill_path.rel_path,
                skills_folder / skill_path.skill_name,
            )
            for package_key, package in selected_packages
            for skill_path in package.skill_paths
        ]
        for source, destination in links:
            try:
                link_creator.validate_directory_link_for_removal(source, destination)
            except OSError as error:
                raise PyConjuryError(str(error)) from error

        if not shared_package:
            _uninstall_tool(package_name)

        for source, destination in links:
            try:
                link_creator.remove_directory_link(source, destination)
            except OSError as error:
                raise PyConjuryError(str(error)) from error

        for package_key, _ in selected_packages:
            package_file = storage.root_folder / f"{package_key}.toml"
            try:
                package_file.unlink()
            except OSError as error:
                raise PyConjuryError(f"Cannot remove package metadata {package_file}: {error}") from error

        return not shared_package, removed_skill_names

    def _install_package(
        self,
        storage: PyconjuryStorage,
        package_folder: Path,
        package_link: PackageLink,
        install_source: str | Path,
    ) -> PackageSkills:
        searcher = SkillSearcher(package_folder)
        skill_paths = searcher.infer_public_skill_paths()
        link_creator = create_default_file_system_link_creator()
        if not skill_paths:
            raise PyConjuryError(f"No public Skills with an installed CLI command were found in {install_source}.")

        package_name = _read_package_name(package_folder)
        try:
            storage.root_folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PyConjuryError(f"Cannot create package storage {storage.root_folder}: {error}") from error

        package_skills = PackageSkills(
            package_link=package_link,
            skill_paths=skill_paths,
            package_name=package_name,
        )
        package_file = storage.root_folder / f"{package_folder.name}.toml"
        _check_existing_package_file(package_file, package_skills)
        skills_folder = _agents_skills_folder()
        for skill_path in skill_paths:
            target = package_folder / skill_path.rel_path
            link_path = skills_folder / skill_path.skill_name
            link_creator.validate_directory_link(target, link_path)

        _install_tool(install_source)
        for skill_path in skill_paths:
            target = package_folder / skill_path.rel_path
            link_path = skills_folder / skill_path.skill_name
            link_creator.create_directory_link(target, link_path)

        package_skills.write_toml_file(package_file)
        return package_skills


def _agents_skills_folder() -> Path:
    return Path.home() / ".agents" / "skills"


def _matches_package_source(target: str, package_link: PackageLink) -> bool:
    if isinstance(package_link, GithubPackageURL):
        return target == package_link.url
    return Path(target).expanduser().resolve() == package_link.path.expanduser().resolve()


def _normalize_package_name(package_name: str) -> str:
    return re.sub(r"[-_.]+", "-", package_name).casefold()


def _package_folder_for(storage: PyconjuryStorage, package_key: str, package: PackageSkills) -> Path:
    if isinstance(package.package_link, GithubPackageURL):
        return storage.github_folder / package_key
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


def _check_existing_package_file(package_file: Path, package_skills: PackageSkills) -> None:
    if not package_file.exists():
        return

    existing_package = PackageSkills.from_toml_file(package_file)
    if existing_package.package_link != package_skills.package_link:
        raise PyConjuryError(f"Cannot replace package metadata for a different package source: {package_file}")


def _is_github_source(source: str) -> bool:
    clean_source = source.removeprefix("git+")
    return clean_source.lower().startswith("git@github.com:") or urlsplit(clean_source).scheme.lower() in {
        "https",
        "ssh",
    }


def _install_tool(source: str | Path) -> None:
    if isinstance(source, Path):
        package_source = str(source)
    else:
        url = source
        git_url = url.removeprefix("git+")
        if git_url.startswith("git@github.com:"):
            package_source = f"git+ssh://git@github.com/{git_url.removeprefix('git@github.com:')}"
        elif url.startswith("git+"):
            package_source = url
        else:
            package_source = f"git+{git_url}"
    try:
        subprocess.run(
            ["uv", "tool", "install", "--force", "--refresh", package_source],
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise PyConjuryError("uv is required to install the Python package but was not found.") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise PyConjuryError(f"uv tool install failed: {detail or 'uv reported no details.'}") from error


def _uninstall_tool(package_name: str) -> None:
    try:
        subprocess.run(
            ["uv", "tool", "uninstall", package_name],
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise PyConjuryError("uv is required to uninstall the Python package but was not found.") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise PyConjuryError(f"uv tool uninstall failed: {detail or 'uv reported no details.'}") from error
