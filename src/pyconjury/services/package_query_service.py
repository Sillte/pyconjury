from typing import Sequence

from pyconjury.models.errors import PyConjuryError
from pyconjury.models.links import SkillPath
from pyconjury.models.package_skills import PackageSkills
from pyconjury.models.storage import PyconjuryStorage

from .service_helpers import _normalize_package_name, _package_folder_for, _read_package_name


class ConjuryPackageQueryService:
    def list_packages(self) -> Sequence[tuple[str, PackageSkills]]:
        storage = PyconjuryStorage.from_storage_folder()
        packages: list[tuple[str, PackageSkills]] = []
        for package_key in storage.package_names:
            package = storage.get_package_skills(package_key)
            package_name = package.package_name or _read_package_name(
                _package_folder_for(storage, package)
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
