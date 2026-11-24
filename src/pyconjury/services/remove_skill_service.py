from dataclasses import dataclass
from pathlib import Path

from pyconjury.infra.filesystem_link_creator import create_default_file_system_link_creator
from pyconjury.models.errors import PyConjuryError
from pyconjury.models.links import SkillPath
from pyconjury.models.package_skills import PackageSkills
from pyconjury.models.storage import PyconjuryStorage

from .service_helpers import _agents_skills_folder, _package_folder_for, _read_package_name


@dataclass(frozen=True)
class _RemoveSkillPlan:
    package_skills: PackageSkills
    package_file: Path
    source: Path
    destination: Path


class ConjuryRemoveSkillService:
    def remove_skill(self, skill_name: str) -> None:
        plan = self._prepare_remove_skill(skill_name)
        self._execute_remove_skill(plan)

    def _prepare_remove_skill(self, skill_name: str) -> _RemoveSkillPlan:
        storage = PyconjuryStorage.from_storage_folder()
        matches: list[tuple[str, PackageSkills, SkillPath]] = []
        for package_key in storage.package_names:
            package = storage.get_package_skills(package_key)
            for skill_path in package.skill_paths:
                if skill_path.skill_name.casefold() == skill_name.casefold():
                    matches.append((package_key, package, skill_path))
        if not matches:
            raise PyConjuryError(f"No installed Skill matches {skill_name!r}.")
        if len(matches) > 1:
            registrations = sorted(
                {
                    f"{package.package_name or _read_package_name(_package_folder_for(storage, package))} "
                    f"({package_key})"
                    for package_key, package, _ in matches
                },
                key=str.casefold,
            )
            raise PyConjuryError(
                f"Multiple installed Skills match {skill_name!r}; resolve the duplicate registrations first "
                f"({', '.join(registrations)})."
            )

        package_key, package, selected_skill = matches[0]
        package_folder = _package_folder_for(storage, package)
        remaining_skill_paths = [
            skill_path for skill_path in package.skill_paths if skill_path != selected_skill
        ]
        updated_package = PackageSkills(
            package_link=package.package_link,
            skill_paths=remaining_skill_paths,
            package_name=package.package_name,
        )
        source = package_folder / selected_skill.rel_path
        destination = _agents_skills_folder() / selected_skill.skill_name
        link_creator = create_default_file_system_link_creator()
        try:
            link_creator.validate_directory_link_for_removal(source, destination)
        except OSError as error:
            raise PyConjuryError(str(error)) from error

        return _RemoveSkillPlan(
            package_skills=updated_package,
            package_file=storage.root_folder / f"{package_key}.toml",
            source=source,
            destination=destination,
        )

    def _execute_remove_skill(self, plan: _RemoveSkillPlan) -> None:
        link_creator = create_default_file_system_link_creator()
        try:
            link_creator.remove_directory_link(plan.source, plan.destination)
        except OSError as error:
            raise PyConjuryError(str(error)) from error
        plan.package_skills.write_toml_file(plan.package_file)
