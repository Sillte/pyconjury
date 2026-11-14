from pathlib import Path
from types import SimpleNamespace

import pytest

from pyconjury.models.links import LocalPackagePath, SkillPath
from pyconjury.models.package_skills import PackageSkills
from pyconjury.services.doctor_service import ConjuryDoctorService


def create_registered_package(
    storage_folder: Path,
    package_folder: Path,
    package_name: str = "sample",
    skill_name: str = "public",
) -> None:
    package_folder.mkdir()
    (package_folder / "pyproject.toml").write_text(
        f'[project]\nname = "{package_name}"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    skill_folder = package_folder / "skills" / skill_name
    skill_folder.mkdir(parents=True)
    (skill_folder / "SKILL.md").write_text(f"Run `uvx {package_name} --help`.", encoding="utf-8")
    PackageSkills(
        package_link=LocalPackagePath(path=package_folder.resolve()),
        skill_paths=[SkillPath(rel_path=Path("skills") / skill_name)],
        package_name=package_name,
    ).write_toml_file(storage_folder / f"{package_name}.toml")


def test_check_reports_consistent_package_and_skill_installation(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "storage"
    storage_folder.mkdir()
    package_folder = tmp_path / "package"
    create_registered_package(storage_folder, package_folder)
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.doctor_service._agents_skills_folder", lambda: tmp_path / "skills")
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(validate_directory_link_for_removal=lambda _source, _destination: True),
    )
    run_calls = []

    def fake_run(args, **kwargs):
        run_calls.append((args, kwargs))
        return SimpleNamespace(stdout="sample v1.0.0\n- sample\n")

    monkeypatch.setattr("pyconjury.services.doctor_service.subprocess.run", fake_run)

    assert ConjuryDoctorService().check() == []
    assert run_calls[0][0] == ["uv", "tool", "list"]
    assert run_calls[0][1]["errors"] == "replace"


def test_check_reports_invalid_metadata_and_missing_installation_parts(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "storage"
    storage_folder.mkdir()
    (storage_folder / "invalid.toml").write_text("[", encoding="utf-8")
    PackageSkills(
        package_link=LocalPackagePath(path=tmp_path / "missing-package"),
        skill_paths=[SkillPath(rel_path=Path("skills/public"))],
        package_name="missing-package",
    ).write_toml_file(storage_folder / "missing-package.toml")
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.doctor_service._agents_skills_folder", lambda: tmp_path / "skills")
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(validate_directory_link_for_removal=lambda _source, _destination: False),
    )
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=""),
    )

    issues = ConjuryDoctorService().check()

    assert any("Invalid PackageSkills TOML" in issue for issue in issues)
    assert any("Package source directory is missing" in issue for issue in issues)
    assert any("Skill folder is missing" in issue for issue in issues)
    assert any("Skill link is missing" in issue for issue in issues)
    assert any("CLI tool is not installed by uv" in issue for issue in issues)


def test_check_reports_skill_links_that_point_elsewhere(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "storage"
    storage_folder.mkdir()
    package_folder = tmp_path / "package"
    create_registered_package(storage_folder, package_folder)
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.doctor_service._agents_skills_folder", lambda: tmp_path / "skills")

    def validate_link(_source: Path, _destination: Path) -> bool:
        raise FileExistsError("destination points elsewhere")

    monkeypatch.setattr(
        "pyconjury.services.doctor_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(validate_directory_link_for_removal=validate_link),
    )
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="sample v1.0.0\n"),
    )

    issues = ConjuryDoctorService().check()

    assert len(issues) == 1
    assert "Invalid Skill link" in issues[0]
    assert "destination points elsewhere" in issues[0]


def test_check_reports_when_uv_is_not_available(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "storage"
    storage_folder.mkdir()
    create_registered_package(storage_folder, tmp_path / "package")
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.doctor_service._agents_skills_folder", lambda: tmp_path / "skills")
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(validate_directory_link_for_removal=lambda _source, _destination: True),
    )

    def missing_uv(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("pyconjury.services.doctor_service.subprocess.run", missing_uv)

    issues = ConjuryDoctorService().check()

    assert issues == ["Cannot check installed CLI tools: uv was not found."]


def test_check_filters_by_package_and_skill(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "storage"
    storage_folder.mkdir()
    package_folder = tmp_path / "package"
    other_package_folder = tmp_path / "other-package"
    create_registered_package(storage_folder, package_folder)
    create_registered_package(storage_folder, other_package_folder, "other", "extra")
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.doctor_service._agents_skills_folder", lambda: tmp_path / "skills")
    checked_links: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link_for_removal=lambda source, destination: checked_links.append((source, destination))
            or True
        ),
    )
    run_calls = []

    def fake_run(args, **kwargs):
        run_calls.append((args, kwargs))
        return SimpleNamespace(stdout="sample v1.0.0\n")

    monkeypatch.setattr("pyconjury.services.doctor_service.subprocess.run", fake_run)

    assert ConjuryDoctorService().check(package_name="sample", skill_name="public") == []
    assert checked_links == [(package_folder / "skills/public", tmp_path / "skills" / "public")]
    assert run_calls[0][0] == ["uv", "tool", "list"]


def test_check_by_skill_skips_package_and_uv_checks(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "storage"
    storage_folder.mkdir()
    package_folder = tmp_path / "package"
    other_package_folder = tmp_path / "other-package"
    create_registered_package(storage_folder, package_folder)
    create_registered_package(storage_folder, other_package_folder, "other", "extra")
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.doctor_service._agents_skills_folder", lambda: tmp_path / "skills")
    checked_links: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link_for_removal=lambda source, destination: checked_links.append((source, destination))
            or True
        ),
    )
    def fail_uv(*_args, **_kwargs):
        raise AssertionError("uv should not be checked")

    monkeypatch.setattr("pyconjury.services.doctor_service.subprocess.run", fail_uv)

    assert ConjuryDoctorService().check(skill_name="extra") == []
    assert checked_links == [(other_package_folder / "skills/extra", tmp_path / "skills" / "extra")]


@pytest.mark.parametrize(
    ("filters", "expected_issue"),
    [
        ({"package_name": "missing"}, "No installed package matches 'missing'."),
        ({"skill_name": "missing"}, "No registered Skill matches 'missing'."),
        (
            {"package_name": "sample", "skill_name": "missing"},
            "No registered Skill 'missing' matches package 'sample'.",
        ),
    ],
)
def test_check_reports_when_filter_matches_nothing(
    monkeypatch,
    tmp_path: Path,
    filters: dict[str, str],
    expected_issue: str,
) -> None:
    storage_folder = tmp_path / "storage"
    storage_folder.mkdir()
    create_registered_package(storage_folder, tmp_path / "package")
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))

    assert ConjuryDoctorService().check(**filters) == [expected_issue]
