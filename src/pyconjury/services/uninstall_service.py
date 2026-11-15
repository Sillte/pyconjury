import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pyconjury.infra.filesystem_link_creator import create_default_file_system_link_creator
from pyconjury.models.errors import PyConjuryError
from pyconjury.models.storage import PyconjuryStorage

from .service_helpers import (
    _agents_skills_folder,
    _matches_package_source,
    _normalize_package_name,
    _package_folder_for,
    _read_package_name,
)


@dataclass(frozen=True)
class _UninstallPlan:
    package_name: str
    shared_package: bool
    removed_skill_names: Sequence[str]
    links: tuple[tuple[Path, Path], ...]
    package_files: tuple[Path, ...]


class ConjuryUninstallService:
    def uninstall(self, target: str) -> tuple[bool, Sequence[str]]:
        plan = self._prepare_uninstall(target)
        self._execute_uninstall(plan)
        return not plan.shared_package, plan.removed_skill_names

    def _prepare_uninstall(self, target: str) -> _UninstallPlan:
        storage = PyconjuryStorage.from_storage_folder()
        packages = [(name, storage.get_package_skills(name)) for name in storage.package_names]
        source_matches = [entry for entry in packages if _matches_package_source(target, entry[1].package_link)]
        if len(source_matches) > 1:
            package_names = sorted(
                {
                    package.package_name or _read_package_name(_package_folder_for(storage, name, package))
                    for name, package in source_matches
                },
                key=str.casefold,
            )
            raise PyConjuryError(
                f"Multiple installed packages match {target!r}; uninstall by package name instead "
                f"({', '.join(package_names)})."
            )

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
            (skill_path.skill_name for _, package in selected_packages for skill_path in package.skill_paths),
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

        return _UninstallPlan(
            package_name=package_name,
            shared_package=shared_package,
            removed_skill_names=removed_skill_names,
            links=tuple(links),
            package_files=tuple(storage.root_folder / f"{package_key}.toml" for package_key, _ in selected_packages),
        )

    def _execute_uninstall(self, plan: _UninstallPlan) -> None:
        if not plan.shared_package:
            _uninstall_tool(plan.package_name)

        link_creator = create_default_file_system_link_creator()
        for source, destination in plan.links:
            try:
                link_creator.remove_directory_link(source, destination)
            except OSError as error:
                raise PyConjuryError(str(error)) from error

        for package_file in plan.package_files:
            try:
                package_file.unlink()
            except OSError as error:
                raise PyConjuryError(f"Cannot remove package metadata {package_file}: {error}") from error


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
