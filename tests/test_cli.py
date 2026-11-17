from pathlib import Path

import pytest
from click.testing import CliRunner

from pyconjury.cli import main
from pyconjury.models.links import GithubPackageURL, LocalPackagePath, SkillPath
from pyconjury.models.package_skills import PackageSkills


@pytest.mark.parametrize("force", [False, True])
def test_install_passes_local_path_and_force_to_installer(monkeypatch, tmp_path: Path, force: bool) -> None:
    received_sources: list[str] = []
    received_force: list[bool] = []
    package_skills = PackageSkills(
        package_link=LocalPackagePath(path=tmp_path.resolve()),
        skill_paths=[SkillPath(rel_path=Path("skills/public"))],
    )

    class FakeInstallerService:
        def install(self, source: str, *, force: bool = False) -> PackageSkills:
            received_sources.append(source)
            received_force.append(force)
            return package_skills

    monkeypatch.setattr("pyconjury.cli.ConjuryInstallService", FakeInstallerService)

    arguments = ["install"]
    if force:
        arguments.append("--force")
    arguments.append(str(tmp_path))
    result = CliRunner().invoke(main, arguments)

    assert result.exit_code == 0
    assert received_sources == [str(tmp_path)]
    assert received_force == [force]
    assert "Installed public Skills" in result.output
    assert "public" in result.output


def test_uninstall_passes_source_to_installer(monkeypatch) -> None:
    received_sources: list[str] = []

    class FakeInstallerService:
        def uninstall(self, source: str) -> tuple[bool, list[str]]:
            received_sources.append(source)
            return True, ["public"]

    monkeypatch.setattr("pyconjury.cli.ConjuryUninstallService", FakeInstallerService)

    result = CliRunner().invoke(main, ["uninstall", "sample"])

    assert result.exit_code == 0
    assert received_sources == ["sample"]
    assert result.output == "Uninstalled sample and removed its public Skills: public.\n"


def test_uninstall_help_uses_source_as_argument_name() -> None:
    result = CliRunner().invoke(main, ["uninstall", "--help"])

    assert result.exit_code == 0
    assert "SOURCE" in result.output


def test_uninstall_displays_removed_skills_when_tool_is_shared(monkeypatch) -> None:
    class FakeInstallerService:
        def uninstall(self, _source: str) -> tuple[bool, list[str]]:
            return False, ["public"]

    monkeypatch.setattr("pyconjury.cli.ConjuryUninstallService", FakeInstallerService)

    result = CliRunner().invoke(main, ["uninstall", "sample"])

    assert result.exit_code == 0
    assert result.output == "Removed public Skills for sample: public; kept the uv tool used by another package.\n"


def test_skill_remove_passes_skill_name_to_installer(monkeypatch) -> None:
    removed_skills: list[str] = []

    class FakeInstallerService:
        def remove_skill(self, skill_name: str) -> None:
            removed_skills.append(skill_name)

    monkeypatch.setattr("pyconjury.cli.ConjuryRemoveSkillService", FakeInstallerService)

    result = CliRunner().invoke(main, ["skill", "remove", "public"])

    assert result.exit_code == 0
    assert removed_skills == ["public"]
    assert result.output == "Removed Skill public.\n"


def test_list_displays_packages_and_their_skills(monkeypatch, tmp_path: Path) -> None:
    package_skills = PackageSkills(
        package_link=LocalPackagePath(path=tmp_path.resolve()),
        skill_paths=[
            SkillPath(rel_path=Path("skills/zebra")),
            SkillPath(rel_path=Path("skills/apple")),
        ],
        package_name="sample",
    )

    class FakeInstallerService:
        def list_packages(self) -> list[tuple[str, PackageSkills]]:
            return [("sample", package_skills)]

    monkeypatch.setattr("pyconjury.cli.ConjuryPackageQueryService", FakeInstallerService)

    result = CliRunner().invoke(main, ["list"])

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "sample",
        f"  source: local {tmp_path.resolve()}",
        "  apple",
        "  zebra",
    ]


def test_list_displays_github_source_for_package(monkeypatch) -> None:
    package_skills = PackageSkills(
        package_link=GithubPackageURL(url="https://github.com/example/sample"),
        skill_paths=[SkillPath(rel_path=Path("skills/public"))],
        package_name="sample",
    )

    class FakeInstallerService:
        def list_packages(self) -> list[tuple[str, PackageSkills]]:
            return [("sample", package_skills)]

    monkeypatch.setattr("pyconjury.cli.ConjuryPackageQueryService", FakeInstallerService)

    result = CliRunner().invoke(main, ["list"])

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "sample",
        "  source: https://github.com/example/sample",
        "  public",
    ]


def test_list_masks_password_in_github_source(monkeypatch) -> None:
    package_skills = PackageSkills(
        package_link=GithubPackageURL(url="ssh://git:top-secret@github.com/example/sample.git"),
        skill_paths=[SkillPath(rel_path=Path("skills/public"))],
        package_name="sample",
    )

    class FakeInstallerService:
        def list_packages(self) -> list[tuple[str, PackageSkills]]:
            return [("sample", package_skills)]

    monkeypatch.setattr("pyconjury.cli.ConjuryPackageQueryService", FakeInstallerService)

    result = CliRunner().invoke(main, ["list"])

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "sample",
        "  source: ssh://git:****@github.com/example/sample.git",
        "  public",
    ]


def test_list_filters_skills_by_package(monkeypatch) -> None:
    received_packages: list[str] = []
    skill_paths = [SkillPath(rel_path=Path("skills/public"))]

    class FakeInstallerService:
        def list_skills(self, package_name: str) -> list[SkillPath]:
            received_packages.append(package_name)
            return skill_paths

    monkeypatch.setattr("pyconjury.cli.ConjuryPackageQueryService", FakeInstallerService)

    result = CliRunner().invoke(main, ["list", "--package", "sample"])

    assert result.exit_code == 0
    assert received_packages == ["sample"]
    assert result.output.splitlines() == ["public"]


def test_doctor_reports_consistent_installation(monkeypatch) -> None:
    class FakeDoctorService:
        def check(self, **_filters: str | None) -> list[str]:
            return []

    monkeypatch.setattr("pyconjury.cli.ConjuryDoctorService", FakeDoctorService)

    result = CliRunner().invoke(main, ["doctor"])

    assert result.exit_code == 0
    assert result.output == "All registered packages and Skills are consistent.\n"


def test_doctor_exits_nonzero_and_lists_issues(monkeypatch) -> None:
    class FakeDoctorService:
        def check(self, **_filters: str | None) -> list[str]:
            return ["sample: Skill link is missing."]

    monkeypatch.setattr("pyconjury.cli.ConjuryDoctorService", FakeDoctorService)

    result = CliRunner().invoke(main, ["doctor"])

    assert result.exit_code == 1
    assert result.output == "Installation issues found:\n- sample: Skill link is missing.\n"


def test_doctor_passes_package_and_skill_filters(monkeypatch) -> None:
    received_filters = []

    class FakeDoctorService:
        def check(self, **filters: str | None) -> list[str]:
            received_filters.append(filters)
            return []

    monkeypatch.setattr("pyconjury.cli.ConjuryDoctorService", FakeDoctorService)

    result = CliRunner().invoke(main, ["doctor", "--package", "sample", "--skill", "public"])

    assert result.exit_code == 0
    assert received_filters == [{"package_name": "sample", "skill_name": "public"}]
    assert result.output == "No issues found for the selected package and Skill.\n"


def test_doctor_prune_dry_run_passes_filters_and_displays_plan(monkeypatch) -> None:
    received_calls = []

    class FakeDoctorService:
        def prune(self, **filters):
            received_calls.append(filters)
            return ["Would remove broken Skill 'public' from package 'sample'."], []

    monkeypatch.setattr("pyconjury.cli.ConjuryDoctorService", FakeDoctorService)

    result = CliRunner().invoke(
        main,
        ["doctor", "--prune", "--dry-run", "--package", "sample", "--skill", "public"],
    )

    assert result.exit_code == 1
    assert received_calls == [{"package_name": "sample", "skill_name": "public", "dry_run": True}]
    assert result.output == "Prune plan:\n- Would remove broken Skill 'public' from package 'sample'.\n"


def test_doctor_prune_applies_without_dry_run(monkeypatch) -> None:
    received_calls = []

    class FakeDoctorService:
        def prune(self, **filters):
            received_calls.append(filters)
            return ["Removed broken Skill 'public' from package 'sample'."], []

    monkeypatch.setattr("pyconjury.cli.ConjuryDoctorService", FakeDoctorService)

    result = CliRunner().invoke(main, ["doctor", "--prune"])

    assert result.exit_code == 0
    assert received_calls == [{"package_name": None, "skill_name": None, "dry_run": False}]
    assert result.output == "Prune results:\n- Removed broken Skill 'public' from package 'sample'.\n"


def test_doctor_rejects_dry_run_without_prune() -> None:
    result = CliRunner().invoke(main, ["doctor", "--dry-run"])

    assert result.exit_code == 2
    assert "--dry-run can only be used with --prune" in result.output
