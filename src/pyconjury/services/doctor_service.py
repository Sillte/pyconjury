import re
import subprocess
import tomllib
from pathlib import Path
from typing import Sequence

from pyconjury.infra.filesystem_link_creator import create_default_file_system_link_creator
from pyconjury.models.errors import PyConjuryError
from pyconjury.models.links import GithubPackageURL, SkillPath
from pyconjury.models.package_skills import PackageSkills
from pyconjury.models.storage import PyconjuryStorage


class ConjuryDoctorService:
    def check(self, package_name: str | None = None, skill_name: str | None = None) -> Sequence[str]:
        storage_folder = PyconjuryStorage.resolve_storage_folder()
        if storage_folder.exists() and not storage_folder.is_dir():
            return [f"Package storage is not a directory: {storage_folder}"]

        issues: list[str] = []
        package_entries: list[tuple[Path, PackageSkills]] = []
        for package_file in sorted(storage_folder.glob("*.toml")):
            try:
                package = PackageSkills.from_toml_file(package_file)
            except PyConjuryError as error:
                if package_name is None and skill_name is None:
                    issues.append(str(error))
                continue
            package_entries.append((package_file, package))

        package_matches = [
            (package_file, package)
            for package_file, package in package_entries
            if package_name is None or _matches_package_name(storage_folder, package_file.stem, package, package_name)
        ]
        if package_name is not None and not package_matches:
            return [f"No installed package matches {package_name!r}."]

        selected_packages: list[tuple[Path, PackageSkills, Sequence[SkillPath]]] = []
        for package_file, package in package_matches:
            selected_skills = [
                skill_path
                for skill_path in package.skill_paths
                if skill_name is None or skill_path.skill_name.casefold() == skill_name.casefold()
            ]
            if selected_skills or skill_name is None:
                selected_packages.append((package_file, package, selected_skills))

        if skill_name is not None and not selected_packages:
            if package_name is not None:
                return [f"No registered Skill {skill_name!r} matches package {package_name!r}."]
            return [f"No registered Skill matches {skill_name!r}."]

        check_package = skill_name is None or package_name is not None
        expected_tool_names: set[str] = set()
        skills_folder = _agents_skills_folder()
        link_creator = create_default_file_system_link_creator()

        for package_file, package, selected_skills in selected_packages:
            package_folder = _package_folder_for(storage_folder, package_file.stem, package)
            if check_package:
                project_name = _check_package_source(package_file.stem, package, package_folder, issues)
                registered_name = package.package_name or project_name
                if registered_name:
                    expected_tool_names.add(registered_name)

            for skill_path in selected_skills:
                skill_folder = package_folder / skill_path.rel_path
                if not skill_folder.is_dir():
                    issues.append(f"{package_file.stem}: Skill folder is missing: {skill_folder}")
                elif not (skill_folder / "SKILL.md").is_file():
                    issues.append(f"{package_file.stem}: SKILL.md is missing: {skill_folder / 'SKILL.md'}")

                skill_link = skills_folder / skill_path.skill_name
                try:
                    link_exists = link_creator.validate_directory_link_for_removal(skill_folder, skill_link)
                except OSError as error:
                    issues.append(f"{package_file.stem}: Invalid Skill link {skill_link}: {error}")
                else:
                    if not link_exists:
                        issues.append(f"{package_file.stem}: Skill link is missing: {skill_link}")

        if expected_tool_names:
            _check_uv_tools(expected_tool_names, issues)
        return issues


def _agents_skills_folder() -> Path:
    return Path.home() / ".agents" / "skills"


def _package_folder_for(storage_folder: Path, package_key: str, package: PackageSkills) -> Path:
    if isinstance(package.package_link, GithubPackageURL):
        return storage_folder / "github" / package_key
    return package.package_link.path


def _matches_package_name(
    storage_folder: Path,
    package_key: str,
    package: PackageSkills,
    requested_name: str,
) -> bool:
    registered_name = package.package_name
    if registered_name is None:
        package_folder = _package_folder_for(storage_folder, package_key, package)
        registered_name = _read_project_name(package_folder)
    return registered_name is not None and _normalize_package_name(registered_name) == _normalize_package_name(
        requested_name
    )


def _read_project_name(package_folder: Path) -> str | None:
    pyproject_path = package_folder / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as pyproject_file:
            metadata = tomllib.load(pyproject_file)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = metadata.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else None


def _check_package_source(
    package_key: str,
    package: PackageSkills,
    package_folder: Path,
    issues: list[str],
) -> str | None:
    if not package_folder.is_dir():
        issues.append(f"{package_key}: Package source directory is missing: {package_folder}")
        return None

    pyproject_path = package_folder / "pyproject.toml"
    if not pyproject_path.is_file():
        issues.append(f"{package_key}: pyproject.toml is missing: {pyproject_path}")
        return None

    try:
        with pyproject_path.open("rb") as pyproject_file:
            metadata = tomllib.load(pyproject_file)
    except OSError as error:
        issues.append(f"{package_key}: Cannot read {pyproject_path}: {error}")
        return None
    except tomllib.TOMLDecodeError as error:
        issues.append(f"{package_key}: Invalid {pyproject_path}: {error}")
        return None

    project = metadata.get("project")
    project_name = project.get("name") if isinstance(project, dict) else None
    if not isinstance(project_name, str) or not project_name.strip():
        issues.append(f"{package_key}: pyproject.toml must declare a non-empty [project].name.")
        return None

    project_name = project_name.strip()
    if package.package_name and _normalize_package_name(package.package_name) != _normalize_package_name(project_name):
        issues.append(
            f"{package_key}: Registered package name {package.package_name!r} does not match "
            f"pyproject.toml name {project_name!r}."
        )
    return project_name


def _check_uv_tools(expected_names: set[str], issues: list[str]) -> None:
    try:
        result = subprocess.run(
            ["uv", "tool", "list"],
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        issues.append("Cannot check installed CLI tools: uv was not found.")
        return
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        issues.append(f"Cannot check installed CLI tools: {detail or 'uv tool list failed.'}")
        return

    installed_names = _parse_uv_tool_names(result.stdout)
    for name in sorted(expected_names, key=str.casefold):
        if _normalize_package_name(name) not in installed_names:
            issues.append(f"{name}: CLI tool is not installed by uv.")


def _parse_uv_tool_names(output: str) -> set[str]:
    installed_names: set[str] = set()
    for line in output.splitlines():
        match = re.match(r"^([^\s]+)\s+v?\d", line)
        if match:
            installed_names.add(_normalize_package_name(match.group(1)))
    return installed_names


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()
