import tomllib
from pathlib import Path
from typing import Self, Sequence

import tomli_w
from pydantic import BaseModel, ValidationError

from pyconjury.models.errors import PyConjuryError

from .links import PackageLink, SkillPath


class PackageSkills(BaseModel, frozen=True):
    """This contains skills which corresponds to one package."""

    package_link: PackageLink
    skill_paths: Sequence[SkillPath]
    package_name: str | None = None

    @classmethod
    def from_toml(cls, content: str) -> Self:
        try:
            data = tomllib.loads(content)
        except tomllib.TOMLDecodeError as error:
            raise PyConjuryError(f"Invalid PackageSkills TOML: {error}") from error
        try:
            return cls.model_validate(data)
        except ValidationError as error:
            raise PyConjuryError(f"Invalid PackageSkills data: {error}") from error

    @classmethod
    def from_toml_file(cls, path: Path) -> Self:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            raise PyConjuryError(f"Cannot read PackageSkills TOML file {path}: {error}") from error
        return cls.from_toml(content)

    def to_toml(self) -> str:
        return tomli_w.dumps(self.model_dump(mode="json", exclude_none=True))

    def write_toml_file(self, path: Path) -> None:
        try:
            path.write_text(self.to_toml(), encoding="utf-8")
        except OSError as error:
            raise PyConjuryError(f"Cannot write PackageSkills TOML file {path}: {error}") from error
