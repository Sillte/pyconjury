import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit

from pyconjury.infra.filesystem_link_creator import create_default_file_system_link_creator
from pyconjury.models.errors import PyConjuryError
from pyconjury.models.links import GithubPackageURL, LocalPackagePath, PackageLink, SkillPath
from pyconjury.models.package_skills import PackageSkills
from pyconjury.models.storage import PyconjuryStorage
from pyconjury.skill_searcher import SkillSearcher

from .service_helpers import _agents_skills_folder, _read_package_name


@dataclass(frozen=True)
class _InstallPlan:
    package_skills: PackageSkills
    package_file: Path
    install_source: str | Path
    links: tuple[tuple[Path, Path], ...]
    links_to_remove: tuple[tuple[Path, Path], ...]
    force: bool


class ConjuryInstallService:
    def install(self, source: str | Path, *, force: bool = False) -> PackageSkills:
        if isinstance(source, Path):
            return self.install_local(source, force=force)
        if _is_github_source(source):
            return self.install_github(source, force=force)
        return self.install_local(Path(source), force=force)

    def install_github(self, url: str, *, force: bool = False) -> PackageSkills:
        storage = PyconjuryStorage.from_storage_folder()
        repository_folder = storage.github_storage.fetch(url, update=True)
        return self._install_package(storage, repository_folder, GithubPackageURL(url=url), url, force)

    def install_local(self, path: Path, *, force: bool = False) -> PackageSkills:
        package_folder = path.expanduser().resolve()
        if not package_folder.is_dir():
            raise PyConjuryError(f"Local Python project directory does not exist: {package_folder}")
        if not (package_folder / "pyproject.toml").is_file():
            raise PyConjuryError(f"Local path is not a Python project with pyproject.toml: {package_folder}")
        storage = PyconjuryStorage.from_storage_folder()
        return self._install_package(storage, package_folder, LocalPackagePath(path=package_folder), package_folder, force)

    def _install_package(
        self,
        storage: PyconjuryStorage,
        package_folder: Path,
        package_link: PackageLink,
        install_source: str | Path,
        force: bool,
    ) -> PackageSkills:
        plan = self._prepare_install(storage, package_folder, package_link, install_source, force)
        self._execute_install(storage, plan)
        return plan.package_skills

    def _prepare_install(
        self,
        storage: PyconjuryStorage,
        package_folder: Path,
        package_link: PackageLink,
        install_source: str | Path,
        force: bool,
    ) -> _InstallPlan:
        searcher = SkillSearcher(package_folder)
        skill_paths = searcher.infer_public_skill_paths()
        if not skill_paths:
            raise PyConjuryError(f"No public Skills with an installed CLI command were found in {install_source}.")

        package_name = _read_package_name(package_folder)
        package_skills = PackageSkills(
            package_link=package_link,
            skill_paths=skill_paths,
            package_name=package_name,
        )
        package_file = storage.root_folder / f"{package_folder.name}.toml"
        existing_package = _check_existing_package_file(package_file, package_skills)
        _check_skill_name_collisions(storage, package_file.stem, skill_paths)

        if storage.root_folder.exists() and not storage.root_folder.is_dir():
            raise PyConjuryError(
                f"Cannot create package storage because the path is not a directory: {storage.root_folder}"
            )

        link_creator = create_default_file_system_link_creator()
        skills_folder = _agents_skills_folder()
        links_to_remove: list[tuple[Path, Path]] = []
        if force and existing_package is not None:
            for existing_skill in existing_package.skill_paths:
                source = package_folder / existing_skill.rel_path
                destination = skills_folder / existing_skill.skill_name
                try:
                    link_exists = link_creator.validate_directory_link_for_removal(source, destination)
                except OSError as error:
                    raise PyConjuryError(str(error)) from error
                if link_exists:
                    links_to_remove.append((source, destination))

        replaceable_destinations = {destination for _, destination in links_to_remove}
        links = tuple(
            (
                package_folder / skill_path.rel_path,
                skills_folder / skill_path.skill_name,
            )
            for skill_path in skill_paths
        )
        for target, link_path in links:
            if link_path in replaceable_destinations:
                try:
                    target.resolve(strict=True)
                except OSError as error:
                    raise PyConjuryError(f"Cannot create Skill link because its target is unavailable: {target}") from error
                continue
            try:
                link_creator.validate_directory_link(target, link_path)
            except OSError as error:
                raise PyConjuryError(str(error)) from error

        return _InstallPlan(
            package_skills=package_skills,
            package_file=package_file,
            install_source=install_source,
            links=links,
            links_to_remove=tuple(links_to_remove),
            force=force,
        )

    def _execute_install(self, storage: PyconjuryStorage, plan: _InstallPlan) -> None:
        try:
            storage.root_folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PyConjuryError(f"Cannot create package storage {storage.root_folder}: {error}") from error

        if not plan.force:
            plan.package_skills.write_toml_file(plan.package_file)
        _install_tool(plan.install_source)

        link_creator = create_default_file_system_link_creator()
        for source, link_path in plan.links_to_remove:
            try:
                link_creator.remove_directory_link(source, link_path)
            except OSError as error:
                raise PyConjuryError(str(error)) from error

        if plan.force:
            plan.package_skills.write_toml_file(plan.package_file)

        for target, link_path in plan.links:
            try:
                link_creator.create_directory_link(target, link_path)
            except OSError as error:
                raise PyConjuryError(str(error)) from error


def _check_existing_package_file(package_file: Path, package_skills: PackageSkills) -> PackageSkills | None:
    if not package_file.exists():
        return None

    existing_package = PackageSkills.from_toml_file(package_file)
    if existing_package.package_link != package_skills.package_link:
        raise PyConjuryError(f"Cannot replace package metadata for a different package source: {package_file}")
    return existing_package


def _check_skill_name_collisions(
    storage: PyconjuryStorage,
    package_key: str,
    skill_paths: Sequence[SkillPath],
) -> None:
    registered_skill_names: dict[str, set[str]] = {}
    for existing_key in storage.package_names:
        if existing_key == package_key:
            continue
        existing_package = storage.get_package_skills(existing_key)
        for skill_path in existing_package.skill_paths:
            registered_skill_names.setdefault(skill_path.skill_name.casefold(), set()).add(existing_key)

    collisions: dict[str, set[str]] = {}
    for skill_path in skill_paths:
        existing_keys = registered_skill_names.get(skill_path.skill_name.casefold())
        if existing_keys:
            collisions.setdefault(skill_path.skill_name, set()).update(existing_keys)

    if collisions:
        details = "; ".join(
            f"{skill_name!r} (registered by {', '.join(sorted(package_keys))})"
            for skill_name, package_keys in sorted(collisions.items(), key=lambda entry: entry[0].casefold())
        )
        raise PyConjuryError(f"Cannot install Skills because their names are already registered: {details}.")


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
