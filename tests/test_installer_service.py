from pathlib import Path
from types import SimpleNamespace

import pytest

from pyconjury.models.errors import PyConjuryError
from pyconjury.models.links import GithubPackageURL, SkillPath
from pyconjury.models.package_skills import PackageSkills
from pyconjury.services.installer_service import ConjuryInstallerService


def create_public_repository(repository_folder: Path) -> None:
    (repository_folder / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"

[project.scripts]
sample = "sample.cli:main"
""",
        encoding="utf-8",
    )
    skill_folder = repository_folder / "skills" / "public"
    skill_folder.mkdir(parents=True)
    (skill_folder / "SKILL.md").write_text("Run `uvx sample --help`.", encoding="utf-8")


def test_install_github_registers_public_skills_and_creates_links(monkeypatch, tmp_path: Path) -> None:
    repository_folder = tmp_path / "sample-repo"
    repository_folder.mkdir()
    create_public_repository(repository_folder)
    storage_folder = tmp_path / "pyconjury"
    skills_folder = tmp_path / ".agents" / "skills"
    created_links: list[tuple[Path, Path]] = []
    installed_urls: list[str] = []
    fetched_urls: list[tuple[str, bool]] = []

    def fake_fetch(_storage, url: str, *, update: bool) -> Path:
        fetched_urls.append((url, update))
        return repository_folder

    def validate_directory_link(target: Path, link_path: Path) -> None:
        assert target == repository_folder / "skills" / "public"
        assert link_path == skills_folder / "public"

    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.models.github_storage.GitHubLocalStorage.fetch", fake_fetch)
    monkeypatch.setattr("pyconjury.services.installer_service._agents_skills_folder", lambda: skills_folder)
    monkeypatch.setattr("pyconjury.services.installer_service._install_tool", installed_urls.append)
    monkeypatch.setattr(
        "pyconjury.services.installer_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link=validate_directory_link,
            create_directory_link=lambda target, link_path: created_links.append((target, link_path)),
        ),
    )

    result = ConjuryInstallerService().install_github("https://github.com/example/sample-repo")

    assert result.package_link == GithubPackageURL(url="https://github.com/example/sample-repo")
    assert result.skill_paths == [SkillPath(rel_path=Path("skills/public"))]
    assert fetched_urls == [("https://github.com/example/sample-repo", True)]
    assert installed_urls == ["https://github.com/example/sample-repo"]
    assert created_links == [(repository_folder / "skills" / "public", skills_folder / "public")]
    assert PackageSkills.from_toml_file(storage_folder / "sample-repo.toml") == result


def test_install_github_rejects_repositories_without_public_skills(monkeypatch, tmp_path: Path) -> None:
    repository_folder = tmp_path / "private-repo"
    repository_folder.mkdir()
    (repository_folder / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    skill_folder = repository_folder / "skills" / "private"
    skill_folder.mkdir(parents=True)
    (skill_folder / "SKILL.md").write_text("No published command.", encoding="utf-8")
    monkeypatch.setenv("PYCONJURY_HOME", str(tmp_path / "pyconjury"))
    monkeypatch.setattr("pyconjury.models.github_storage.GitHubLocalStorage.fetch", lambda *_args, **_kwargs: repository_folder)
    monkeypatch.setattr(
        "pyconjury.services.installer_service._install_tool",
        lambda _url: pytest.fail("tool should not be installed"),
    )

    with pytest.raises(PyConjuryError, match="No public Skills"):
        ConjuryInstallerService().install_github("https://github.com/example/private-repo")

    assert not list((tmp_path / "pyconjury").glob("*.toml"))


def test_install_tool_passes_github_url_to_uv(monkeypatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("pyconjury.services.installer_service.subprocess.run", fake_run)

    from pyconjury.services.installer_service import _install_tool

    _install_tool("https://github.com/example/sample.git")

    assert calls[0][0] == [
        "uv",
        "tool",
        "install",
        "--force",
        "--refresh",
        "git+https://github.com/example/sample.git",
    ]
