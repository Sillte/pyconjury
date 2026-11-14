from pathlib import Path

from click.testing import CliRunner

from pyconjury.cli import main
from pyconjury.models.links import LocalPackagePath, SkillPath
from pyconjury.models.package_skills import PackageSkills


def test_install_passes_local_path_to_installer(monkeypatch, tmp_path: Path) -> None:
    received_sources: list[str] = []
    package_skills = PackageSkills(
        package_link=LocalPackagePath(path=tmp_path.resolve()),
        skill_paths=[SkillPath(rel_path=Path("skills/public"))],
    )

    class FakeInstallerService:
        def install(self, source: str) -> PackageSkills:
            received_sources.append(source)
            return package_skills

    monkeypatch.setattr("pyconjury.cli.ConjuryInstallerService", FakeInstallerService)

    result = CliRunner().invoke(main, ["install", str(tmp_path)])

    assert result.exit_code == 0
    assert received_sources == [str(tmp_path)]
    assert "Installed public Skills" in result.output
    assert "public" in result.output


def test_uninstall_passes_package_name_to_installer(monkeypatch) -> None:
    received_packages: list[str] = []

    class FakeInstallerService:
        def uninstall(self, package: str) -> bool:
            received_packages.append(package)
            return True

    monkeypatch.setattr("pyconjury.cli.ConjuryInstallerService", FakeInstallerService)

    result = CliRunner().invoke(main, ["uninstall", "sample"])

    assert result.exit_code == 0
    assert received_packages == ["sample"]
    assert "Uninstalled sample" in result.output


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

    monkeypatch.setattr("pyconjury.cli.ConjuryInstallerService", FakeInstallerService)

    result = CliRunner().invoke(main, ["list"])

    assert result.exit_code == 0
    assert result.output.splitlines() == ["sample", "  apple", "  zebra"]


def test_list_filters_skills_by_package(monkeypatch) -> None:
    received_packages: list[str] = []
    skill_paths = [SkillPath(rel_path=Path("skills/public"))]

    class FakeInstallerService:
        def list_skills(self, package_name: str) -> list[SkillPath]:
            received_packages.append(package_name)
            return skill_paths

    monkeypatch.setattr("pyconjury.cli.ConjuryInstallerService", FakeInstallerService)

    result = CliRunner().invoke(main, ["list", "--package", "sample"])

    assert result.exit_code == 0
    assert received_packages == ["sample"]
    assert result.output.splitlines() == ["public"]
