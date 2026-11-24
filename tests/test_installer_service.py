from pathlib import Path
from types import SimpleNamespace

import pytest

from pyconjury.models.errors import PyConjuryError
from pyconjury.models.github_storage import GitHubLocalStorage
from pyconjury.models.links import GithubPackageURL, LocalPackagePath, SkillPath
from pyconjury.models.package_skills import PackageSkills
from pyconjury.services.doctor_service import ConjuryDoctorService
from pyconjury.services.installer_service import ConjuryInstallService
from pyconjury.services.package_query_service import ConjuryPackageQueryService
from pyconjury.services.remove_skill_service import ConjuryRemoveSkillService
from pyconjury.services.uninstall_service import ConjuryUninstallService, _uninstall_tool


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

    result = ConjuryInstallService().install("https://github.com/example/sample-repo")

    assert result.package_link == GithubPackageURL(url="https://github.com/example/sample-repo")
    assert result.package_name == "sample"
    assert result.skill_paths == [SkillPath(rel_path=Path("skills/public"))]
    assert fetched_urls == [("https://github.com/example/sample-repo", True)]
    assert installed_urls == ["https://github.com/example/sample-repo"]
    assert created_links == [(repository_folder / "skills" / "public", skills_folder / "public")]
    assert PackageSkills.from_toml_file(storage_folder / "sample-repo.toml") == result


def test_github_package_url_resolves_repository_revision_and_subdirectory() -> None:
    source = GitHubLocalStorage.parse_package_url(
        "https://github.com/example/monorepo/tree/main/packages/tool"
    )

    assert source.repository_url == "https://github.com/example/monorepo"
    assert source.revision == "main"
    assert source.subdirectory == Path("packages/tool")
    assert source.package_key == "monorepo--ref-main--packages%2Ftool"
    assert source.tool_source == "git+https://github.com/example/monorepo@main#subdirectory=packages/tool"


@pytest.mark.parametrize(
    ("url", "revision"),
    [
        ("git+https://github.com/example/monorepo#subdirectory=packages/tool", None),
        ("git+https://github.com/example/monorepo@main#subdirectory=packages/tool", "main"),
        ("git+https://github.com/example/monorepo.git@feature/cli#subdirectory=packages/tool", "feature/cli"),
    ],
)
def test_github_package_url_accepts_uv_vcs_and_subdirectory_syntax(url: str, revision: str | None) -> None:
    source = GitHubLocalStorage.parse_package_url(url)

    assert source.repository_url == "https://github.com/example/monorepo"
    assert source.revision == revision
    assert source.subdirectory == Path("packages/tool")
    assert source.tool_source == (
        "git+https://github.com/example/monorepo"
        + (f"@{revision}" if revision else "")
        + "#subdirectory=packages/tool"
    )


def test_github_package_url_rejects_paths_outside_repository() -> None:
    with pytest.raises(PyConjuryError, match="stay inside the repository"):
        GitHubLocalStorage.parse_package_url(
            "https://github.com/example/monorepo/tree/main/packages/%2E%2E/secret"
        )
    with pytest.raises(PyConjuryError, match="stay inside the repository"):
        GitHubLocalStorage.parse_package_url(
            "git+https://github.com/example/monorepo#subdirectory=packages/%2E%2E/secret"
        )


def test_fetch_github_tree_clones_repository_and_checks_out_requested_ref(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, Path | None]]] = []

    def fake_run_git(*args: str, cwd: Path | None = None) -> str:
        calls.append((args, {"cwd": cwd}))
        return ""

    monkeypatch.setattr(GitHubLocalStorage, "_run_git", staticmethod(fake_run_git))
    github_folder = tmp_path / "github"
    repository_folder = github_folder / "_refs" / "monorepo" / "main"

    result = GitHubLocalStorage(github_folder).fetch(
        "https://github.com/example/monorepo/tree/main/packages/tool"
    )

    assert result == repository_folder
    assert calls == [
        (
            ("clone", "--", "https://github.com/example/monorepo", str(repository_folder)),
            {"cwd": github_folder},
        ),
        (
            ("-C", str(repository_folder), "checkout", "main"),
            {"cwd": None},
        ),
    ]


def test_install_github_monorepo_package_registers_and_uses_subdirectory(
    monkeypatch, tmp_path: Path
) -> None:
    storage_folder = tmp_path / "pyconjury"
    repository_folder = storage_folder / "github" / "_refs" / "monorepo" / "main"
    package_folder = repository_folder / "packages" / "tool"
    package_folder.mkdir(parents=True)
    create_public_repository(package_folder)
    source_url = "git+https://github.com/example/monorepo@main#subdirectory=packages/tool"
    skills_folder = tmp_path / ".agents" / "skills"
    fetched_urls: list[tuple[str, bool]] = []
    installed_sources: list[str | Path] = []
    created_links: list[tuple[Path, Path]] = []

    def fake_fetch(_storage, url: str, *, update: bool) -> Path:
        fetched_urls.append((url, update))
        return repository_folder

    def validate_directory_link(target: Path, link_path: Path) -> None:
        assert target == package_folder / "skills" / "public"
        assert link_path == skills_folder / "public"

    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.models.github_storage.GitHubLocalStorage.fetch", fake_fetch)
    monkeypatch.setattr("pyconjury.services.installer_service._agents_skills_folder", lambda: skills_folder)
    monkeypatch.setattr("pyconjury.services.installer_service._install_tool", installed_sources.append)
    monkeypatch.setattr(
        "pyconjury.services.installer_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link=validate_directory_link,
            create_directory_link=lambda target, link_path: created_links.append((target, link_path)),
        ),
    )
    monkeypatch.setattr("pyconjury.services.doctor_service._agents_skills_folder", lambda: skills_folder)
    monkeypatch.setattr("pyconjury.services.doctor_service._check_uv_tools", lambda _names, _issues: None)
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(validate_directory_link_for_removal=lambda _source, _link: True),
    )

    result = ConjuryInstallService().install(source_url)

    assert result.package_link == GithubPackageURL(url=source_url)
    assert result.package_name == "sample"
    assert result.skill_paths == [SkillPath(rel_path=Path("skills/public"))]
    assert fetched_urls == [(source_url, True)]
    assert installed_sources == [
        "git+https://github.com/example/monorepo@main#subdirectory=packages/tool"
    ]
    assert created_links == [(package_folder / "skills" / "public", skills_folder / "public")]
    assert PackageSkills.from_toml_file(storage_folder / "monorepo--ref-main--packages%2Ftool.toml") == result
    assert GitHubLocalStorage.package_folder(storage_folder / "github", source_url) == package_folder
    assert ConjuryDoctorService().check() == []


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
        ConjuryInstallService().install_github("https://github.com/example/private-repo")

    assert not list((tmp_path / "pyconjury").glob("*.toml"))


def test_install_local_python_project_registers_public_skills(monkeypatch, tmp_path: Path) -> None:
    project_folder = tmp_path / "local-project"
    project_folder.mkdir()
    create_public_repository(project_folder)
    storage_folder = tmp_path / "pyconjury"
    skills_folder = tmp_path / ".agents" / "skills"
    created_links: list[tuple[Path, Path]] = []
    installed_sources: list[str | Path] = []

    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.installer_service._agents_skills_folder", lambda: skills_folder)
    monkeypatch.setattr("pyconjury.services.installer_service._install_tool", installed_sources.append)
    monkeypatch.setattr(
        "pyconjury.services.installer_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link=lambda _target, _link_path: None,
            create_directory_link=lambda target, link_path: created_links.append((target, link_path)),
        ),
    )

    result = ConjuryInstallService().install(str(project_folder))

    assert result.package_link == LocalPackagePath(path=project_folder.resolve())
    assert result.package_name == "sample"
    assert result.skill_paths == [SkillPath(rel_path=Path("skills/public"))]
    assert installed_sources == [project_folder.resolve()]
    assert created_links == [(project_folder / "skills" / "public", skills_folder / "public")]
    assert PackageSkills.from_toml_file(storage_folder / "local-project.toml") == result


def test_force_install_replaces_same_source_skill_links_and_registration(monkeypatch, tmp_path: Path) -> None:
    project_folder = tmp_path / "local-project"
    project_folder.mkdir()
    create_public_repository(project_folder)
    extra_skill_folder = project_folder / "skills" / "extra"
    extra_skill_folder.mkdir()
    (extra_skill_folder / "SKILL.md").write_text("Run `uvx sample --help`.", encoding="utf-8")
    stale_skill_folder = project_folder / "skills" / "stale"
    stale_skill_folder.mkdir()
    (stale_skill_folder / "SKILL.md").write_text("No published command.", encoding="utf-8")

    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    package_file = storage_folder / "local-project.toml"
    PackageSkills(
        package_link=LocalPackagePath(path=project_folder.resolve()),
        skill_paths=[
            SkillPath(rel_path=Path("skills/public")),
            SkillPath(rel_path=Path("skills/stale")),
        ],
        package_name="sample",
    ).write_toml_file(package_file)

    skills_folder = tmp_path / ".agents" / "skills"
    removed_links: list[tuple[Path, Path]] = []
    created_links: list[tuple[Path, Path]] = []
    validated_new_links: list[tuple[Path, Path]] = []
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.installer_service._agents_skills_folder", lambda: skills_folder)
    monkeypatch.setattr("pyconjury.services.installer_service._install_tool", lambda _source: None)
    monkeypatch.setattr(
        "pyconjury.services.installer_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link=lambda source, destination: validated_new_links.append((source, destination))
            or False,
            validate_directory_link_for_removal=lambda _source, _destination: True,
            remove_directory_link=lambda source, destination: removed_links.append((source, destination)),
            create_directory_link=lambda source, destination: created_links.append((source, destination)),
        ),
    )

    result = ConjuryInstallService().install(str(project_folder), force=True)

    assert result.skill_paths == [
        SkillPath(rel_path=Path("skills/extra")),
        SkillPath(rel_path=Path("skills/public")),
    ]
    assert removed_links == [
        (project_folder / "skills/public", skills_folder / "public"),
        (project_folder / "skills/stale", skills_folder / "stale"),
    ]
    assert validated_new_links == [(project_folder / "skills/extra", skills_folder / "extra")]
    assert created_links == [
        (project_folder / "skills/extra", skills_folder / "extra"),
        (project_folder / "skills/public", skills_folder / "public"),
    ]
    assert project_folder.is_dir()
    assert stale_skill_folder.is_dir()
    assert PackageSkills.from_toml_file(package_file) == result


def test_install_rejects_a_skill_name_registered_by_another_package(monkeypatch, tmp_path: Path) -> None:
    project_folder = tmp_path / "new-project"
    project_folder.mkdir()
    create_public_repository(project_folder)
    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    existing_folder = tmp_path / "existing-project"
    existing_folder.mkdir()
    PackageSkills(
        package_link=LocalPackagePath(path=existing_folder.resolve()),
        skill_paths=[SkillPath(rel_path=Path("skills/Public"))],
        package_name="existing",
    ).write_toml_file(storage_folder / "existing-project.toml")
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr(
        "pyconjury.services.installer_service._install_tool",
        lambda _source: pytest.fail("tool should not be installed"),
    )

    with pytest.raises(PyConjuryError, match="already registered"):
        ConjuryInstallService().install(str(project_folder), force=True)

    assert not (storage_folder / "new-project.toml").exists()


def test_install_failure_leaves_registration_for_doctor_to_report(monkeypatch, tmp_path: Path) -> None:
    project_folder = tmp_path / "project"
    project_folder.mkdir()
    create_public_repository(project_folder)
    storage_folder = tmp_path / "pyconjury"
    skills_folder = tmp_path / "skills"

    def fail_install(_source: str | Path) -> None:
        raise PyConjuryError("install failed")

    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.installer_service._agents_skills_folder", lambda: skills_folder)
    monkeypatch.setattr("pyconjury.services.installer_service._install_tool", fail_install)
    monkeypatch.setattr(
        "pyconjury.services.doctor_service._agents_skills_folder",
        lambda: skills_folder,
    )
    monkeypatch.setattr(
        "pyconjury.services.doctor_service._check_uv_tools",
        lambda _names, _issues: None,
    )

    with pytest.raises(PyConjuryError, match="install failed"):
        ConjuryInstallService().install(str(project_folder))

    issues = ConjuryDoctorService().check()

    assert any("Skill link is missing" in issue for issue in issues)


def test_install_local_rejects_paths_without_pyproject(monkeypatch, tmp_path: Path) -> None:
    project_folder = tmp_path / "not-a-project"
    project_folder.mkdir()
    monkeypatch.setenv("PYCONJURY_HOME", str(tmp_path / "pyconjury"))
    monkeypatch.setattr(
        "pyconjury.services.installer_service._install_tool",
        lambda _source: pytest.fail("tool should not be installed"),
    )

    with pytest.raises(PyConjuryError, match="pyproject.toml"):
        ConjuryInstallService().install(str(project_folder))


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
    assert calls[0][1]["errors"] == "replace"


def test_install_tool_passes_local_path_to_uv(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("pyconjury.services.installer_service.subprocess.run", fake_run)

    from pyconjury.services.installer_service import _install_tool

    _install_tool(tmp_path)

    assert calls[0][0] == ["uv", "tool", "install", "--force", "--refresh", str(tmp_path)]


@pytest.mark.parametrize("identifier", ["source", "project_name"])
def test_uninstall_removes_registered_skills_metadata_and_tool(monkeypatch, tmp_path: Path, identifier: str) -> None:
    project_folder = tmp_path / "local-project"
    project_folder.mkdir()
    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    package_file = storage_folder / "local-project.toml"
    package_skills = PackageSkills(
        package_link=LocalPackagePath(path=project_folder.resolve()),
        skill_paths=[SkillPath(rel_path=Path("skills/public"))],
        package_name="sample",
    )
    package_skills.write_toml_file(package_file)
    removed_links: list[tuple[Path, Path]] = []
    uninstalled_tools: list[str] = []
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.uninstall_service._agents_skills_folder", lambda: tmp_path / "skills")
    monkeypatch.setattr(
        "pyconjury.services.uninstall_service._uninstall_tool",
        uninstalled_tools.append,
    )
    monkeypatch.setattr(
        "pyconjury.services.uninstall_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link_for_removal=lambda _source, _destination: True,
            remove_directory_link=lambda source, destination: removed_links.append((source, destination)),
        ),
    )

    target = str(project_folder) if identifier == "source" else "sample"
    tool_removed, removed_skill_names = ConjuryUninstallService().uninstall(target)

    assert tool_removed is True
    assert removed_skill_names == ["public"]
    assert uninstalled_tools == ["sample"]
    assert removed_links == [(project_folder / "skills/public", tmp_path / "skills" / "public")]
    assert not package_file.exists()


def test_uninstall_by_package_name_removes_all_shared_registrations(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    project_folders = [tmp_path / "project-a", tmp_path / "project-b"]
    package_files = []
    for project_folder, package_key, skill_name in zip(project_folders, ("project-a", "project-b"), ("one", "two")):
        project_folder.mkdir()
        package_file = storage_folder / f"{package_key}.toml"
        PackageSkills(
            package_link=LocalPackagePath(path=project_folder.resolve()),
            skill_paths=[SkillPath(rel_path=Path("skills") / skill_name)],
            package_name="sample",
        ).write_toml_file(package_file)
        package_files.append(package_file)

    removed_links: list[tuple[Path, Path]] = []
    uninstalled_tools: list[str] = []
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.uninstall_service._agents_skills_folder", lambda: tmp_path / "skills")
    monkeypatch.setattr("pyconjury.services.uninstall_service._uninstall_tool", uninstalled_tools.append)
    monkeypatch.setattr(
        "pyconjury.services.uninstall_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link_for_removal=lambda _source, _destination: True,
            remove_directory_link=lambda source, destination: removed_links.append((source, destination)),
        ),
    )
    monkeypatch.setattr(
        "pyconjury.models.storage.PyconjuryStorage.package_names",
        property(lambda _storage: ["project-b", "project-a"]),
    )

    tool_removed, removed_skill_names = ConjuryUninstallService().uninstall("sample")

    assert tool_removed is True
    assert removed_skill_names == ["one", "two"]
    assert uninstalled_tools == ["sample"]
    assert removed_links == [
        (project_folders[0] / "skills/one", tmp_path / "skills" / "one"),
        (project_folders[1] / "skills/two", tmp_path / "skills" / "two"),
    ]
    assert all(not package_file.exists() for package_file in package_files)


def test_uninstall_by_source_lists_package_names_when_source_matches_multiple_registrations(
    monkeypatch, tmp_path: Path
) -> None:
    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    project_folder = tmp_path / "project"
    project_folder.mkdir()
    for package_key, package_name in (("project-a", "sample-a"), ("project-b", "sample-b")):
        PackageSkills(
            package_link=LocalPackagePath(path=project_folder.resolve()),
            skill_paths=[SkillPath(rel_path=Path("skills/public"))],
            package_name=package_name,
        ).write_toml_file(storage_folder / f"{package_key}.toml")
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))

    with pytest.raises(PyConjuryError) as error:
        ConjuryUninstallService().uninstall(str(project_folder))

    assert "sample-a, sample-b" in str(error.value)


def test_uninstall_by_package_name_supports_legacy_metadata(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    project_folder = tmp_path / "legacy-project"
    project_folder.mkdir()
    (project_folder / "pyproject.toml").write_text('[project]\nname = "legacy-name"\n', encoding="utf-8")
    package_file = storage_folder / "legacy-repo.toml"
    PackageSkills(
        package_link=LocalPackagePath(path=project_folder.resolve()),
        skill_paths=[SkillPath(rel_path=Path("skills/public"))],
    ).write_toml_file(package_file)
    uninstalled_tools: list[str] = []
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.uninstall_service._agents_skills_folder", lambda: tmp_path / "skills")
    monkeypatch.setattr("pyconjury.services.uninstall_service._uninstall_tool", uninstalled_tools.append)
    monkeypatch.setattr(
        "pyconjury.services.uninstall_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link_for_removal=lambda _source, _destination: False,
            remove_directory_link=lambda _source, _destination: None,
        ),
    )

    tool_removed, removed_skill_names = ConjuryUninstallService().uninstall("legacy-name")

    assert tool_removed is True
    assert removed_skill_names == ["public"]
    assert uninstalled_tools == ["legacy-name"]
    assert not package_file.exists()


def test_uninstall_by_source_keeps_tool_used_by_another_registration(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    project_folders = [tmp_path / "project-a", tmp_path / "project-b"]
    package_file = storage_folder / "project-a.toml"
    other_package_file = storage_folder / "project-b.toml"
    for project_folder in project_folders:
        project_folder.mkdir()
    PackageSkills(
        package_link=LocalPackagePath(path=project_folders[0].resolve()),
        skill_paths=[SkillPath(rel_path=Path("skills/one"))],
        package_name="sample",
    ).write_toml_file(package_file)
    PackageSkills(
        package_link=LocalPackagePath(path=project_folders[1].resolve()),
        skill_paths=[SkillPath(rel_path=Path("skills/two"))],
        package_name="sample",
    ).write_toml_file(other_package_file)

    removed_links: list[tuple[Path, Path]] = []
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.uninstall_service._agents_skills_folder", lambda: tmp_path / "skills")
    monkeypatch.setattr(
        "pyconjury.services.uninstall_service._uninstall_tool",
        lambda _name: pytest.fail("shared uv tool should be kept"),
    )
    monkeypatch.setattr(
        "pyconjury.services.uninstall_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link_for_removal=lambda _source, _destination: True,
            remove_directory_link=lambda source, destination: removed_links.append((source, destination)),
        ),
    )

    tool_removed, removed_skill_names = ConjuryUninstallService().uninstall(str(project_folders[0]))

    assert tool_removed is False
    assert removed_skill_names == ["one"]
    assert removed_links == [(project_folders[0] / "skills/one", tmp_path / "skills" / "one")]
    assert not package_file.exists()
    assert other_package_file.exists()


def test_remove_skill_keeps_package_and_tool_when_last_skill_is_removed(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    package_folder = tmp_path / "package"
    package_folder.mkdir()
    (package_folder / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    skill_paths = [SkillPath(rel_path=Path("skills/public")), SkillPath(rel_path=Path("skills/extra"))]
    for skill_path in skill_paths:
        skill_folder = package_folder / skill_path.rel_path
        skill_folder.mkdir(parents=True)
        (skill_folder / "SKILL.md").write_text("Skill.", encoding="utf-8")
    package_file = storage_folder / "package.toml"
    PackageSkills(
        package_link=LocalPackagePath(path=package_folder.resolve()),
        skill_paths=skill_paths,
        package_name="sample",
    ).write_toml_file(package_file)
    removed_links: list[tuple[Path, Path]] = []
    skills_folder = tmp_path / "agents" / "skills"
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))
    monkeypatch.setattr("pyconjury.services.remove_skill_service._agents_skills_folder", lambda: skills_folder)
    monkeypatch.setattr(
        "pyconjury.services.uninstall_service._uninstall_tool",
        lambda _name: pytest.fail("the package tool should remain installed"),
    )
    monkeypatch.setattr(
        "pyconjury.services.remove_skill_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(
            validate_directory_link_for_removal=lambda _source, _destination: True,
            remove_directory_link=lambda source, destination: removed_links.append((source, destination)),
        ),
    )

    service = ConjuryRemoveSkillService()
    service.remove_skill("public")

    remaining_package = PackageSkills.from_toml_file(package_file)
    assert remaining_package.skill_paths == [SkillPath(rel_path=Path("skills/extra"))]

    service.remove_skill("extra")

    empty_package = PackageSkills.from_toml_file(package_file)
    assert empty_package.skill_paths == []
    assert removed_links == [
        (package_folder / "skills/public", skills_folder / "public"),
        (package_folder / "skills/extra", skills_folder / "extra"),
    ]

    monkeypatch.setattr("pyconjury.services.doctor_service._agents_skills_folder", lambda: skills_folder)
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.create_default_file_system_link_creator",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "pyconjury.services.doctor_service.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="sample v1.0.0\n"),
    )

    assert ConjuryDoctorService().check(package_name="sample") == []


def test_list_packages_and_skills_use_registered_project_names(monkeypatch, tmp_path: Path) -> None:
    storage_folder = tmp_path / "pyconjury"
    storage_folder.mkdir()
    project_folders = [tmp_path / "project-a", tmp_path / "project-b"]
    for project_folder in project_folders:
        project_folder.mkdir()
    PackageSkills(
        package_link=LocalPackagePath(path=project_folders[0]),
        skill_paths=[SkillPath(rel_path=Path("skills/first"))],
        package_name="Sample_Package",
    ).write_toml_file(storage_folder / "project-a.toml")
    PackageSkills(
        package_link=LocalPackagePath(path=project_folders[1]),
        skill_paths=[SkillPath(rel_path=Path("skills/second"))],
        package_name="other",
    ).write_toml_file(storage_folder / "project-b.toml")
    monkeypatch.setenv("PYCONJURY_HOME", str(storage_folder))

    service = ConjuryPackageQueryService()

    assert [name for name, _ in service.list_packages()] == ["other", "Sample_Package"]
    assert [skill.skill_name for skill in service.list_skills("sample-package")] == ["first"]


def test_list_skills_rejects_unknown_package(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYCONJURY_HOME", str(tmp_path / "empty-storage"))

    with pytest.raises(PyConjuryError, match="No installed package"):
        ConjuryPackageQueryService().list_skills("missing")


def test_uninstall_tool_passes_package_name_to_uv(monkeypatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("pyconjury.services.uninstall_service.subprocess.run", fake_run)

    _uninstall_tool("sample")

    assert calls[0][0] == ["uv", "tool", "uninstall", "sample"]
    assert calls[0][1]["errors"] == "replace"
