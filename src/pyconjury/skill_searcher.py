import re
import tomllib
from pathlib import Path
from typing import Mapping, Sequence

from pyconjury.models.errors import PyConjuryError
from pyconjury.models.links import SkillPath


class SkillSearcher:
    def __init__(self, package_folder: Path) -> None:
        self._package_folder = package_folder
        self._name_to_folder = self._construct_skill_paths()

    @property
    def package_folder(self) -> Path:
        return self._package_folder

    def _construct_skill_paths(self) -> Mapping[str, Path]:
        name_to_folder: dict[str, Path] = {}
        for skill_file in self._package_folder.glob("**/SKILL.md"):
            skill_name = skill_file.parent.name
            normalized_name = skill_name.casefold()
            if normalized_name in name_to_folder:
                raise PyConjuryError(
                    f"Multiple Skills named {skill_name!r} were found in {self._package_folder}."
                )
            name_to_folder[normalized_name] = skill_file
        return name_to_folder

    @property
    def skills(self) -> Sequence[str]:
        return sorted((path.parent.name for path in self._name_to_folder.values()), key=str.casefold)

    def infer_public_skills(self) -> Sequence[str]:
        return [skill_path.skill_name for skill_path in self.infer_public_skill_paths()]

    def infer_public_skill_paths(self) -> Sequence[SkillPath]:
        cli_commands = self.get_cli_commands()
        return [
            SkillPath(rel_path=skill_file.parent.relative_to(self._package_folder))
            for skill_file in sorted(self._name_to_folder.values(), key=lambda path: path.parent.name.casefold())
            if self._infer_is_public_skill(skill_file, cli_commands)
        ]

    def _infer_is_public_skill(self, skill_file: Path, cli_commands: Sequence[str]) -> bool:
        content = skill_file.read_text(encoding="utf-8")
        for command in cli_commands:
            escaped_command = re.escape(command)
            for invocation in (rf"uvx[ \t]+{escaped_command}", rf"uv[ \t]+tool[ \t]+run[ \t]+{escaped_command}"):
                if re.search(rf"(?<![\w.-]){invocation}(?=$|[\s`'\"])", content):
                    return True
        return False

    def get_cli_commands(self) -> Sequence[str]:
        pyproject_path = self._package_folder / "pyproject.toml"
        if not pyproject_path.exists():
            return []

        with pyproject_path.open("rb") as pyproject_file:
            project_metadata = tomllib.load(pyproject_file)

        project = project_metadata.get("project", {})
        if not isinstance(project, dict):
            raise ValueError(f"Invalid [project] table in {pyproject_path}.")

        scripts = project.get("scripts", {})
        if not isinstance(scripts, dict):
            raise ValueError(f"Invalid [project.scripts] table in {pyproject_path}.")

        return sorted(scripts)
