from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_serializer, field_validator


class GithubPackageURL(BaseModel, frozen=True):
    type: Literal["github"] = "github"
    url: str


class LocalPackagePath(BaseModel, frozen=True):
    type: Literal["local"] = "local"
    path: Path


type PackageLink = GithubPackageURL | LocalPackagePath


class SkillPath(BaseModel, frozen=True):
    rel_path: Path

    @field_validator("rel_path")
    @classmethod
    def require_relative_path(cls, value: Path) -> Path:
        if not value.parts or value.is_absolute() or ".." in value.parts:
            raise ValueError("Skill paths must be non-empty relative paths inside their package.")
        return value

    @field_serializer("rel_path", when_used="json")
    def serialize_relative_path(self, value: Path) -> str:
        return value.as_posix()

    @property
    def skill_name(self) -> str:
        return self.rel_path.name
