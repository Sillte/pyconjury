from pathlib import Path

import pytest

from pyconjury.models.errors import PyConjuryError
from pyconjury.skill_searcher import SkillSearcher


def test_skill_searcher_rejects_duplicate_skill_names_within_a_package(tmp_path: Path) -> None:
    for skill_path in (tmp_path / "first" / "sample", tmp_path / "second" / "sample"):
        skill_path.mkdir(parents=True)
        (skill_path / "SKILL.md").write_text("Private Skill.", encoding="utf-8")

    with pytest.raises(PyConjuryError, match="Multiple Skills named"):
        SkillSearcher(tmp_path)


def test_get_cli_commands_reads_project_scripts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"

[project.scripts]
sample = "sample.cli:main"
sample-admin = "sample.admin:main"
""",
        encoding="utf-8",
    )

    assert SkillSearcher(tmp_path).get_cli_commands() == ["sample", "sample-admin"]


def test_get_cli_commands_returns_empty_when_project_has_no_scripts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"
""",
        encoding="utf-8",
    )

    assert SkillSearcher(tmp_path).get_cli_commands() == []


def test_get_cli_commands_rejects_malformed_scripts_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
scripts = "not-a-table"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Invalid \[project\.scripts\] table"):
        SkillSearcher(tmp_path).get_cli_commands()


def test_infer_public_skills_requires_a_published_cli_invocation(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"

[project.scripts]
sample = "sample.cli:main"
""",
        encoding="utf-8",
    )
    public_skill = tmp_path / "skills" / "public"
    public_skill.mkdir(parents=True)
    (public_skill / "SKILL.md").write_text(
        "Run `uvx sample --help` to use this workflow.",
        encoding="utf-8",
    )
    unrelated_skill = tmp_path / "skills" / "unrelated"
    unrelated_skill.mkdir(parents=True)
    (unrelated_skill / "SKILL.md").write_text(
        "Run `uvx other-command --help` to use this workflow.",
        encoding="utf-8",
    )
    similar_command_skill = tmp_path / "skills" / "similar-command"
    similar_command_skill.mkdir(parents=True)
    (similar_command_skill / "SKILL.md").write_text(
        "Run `uvx sample-extra --help` to use this workflow.",
        encoding="utf-8",
    )

    assert SkillSearcher(tmp_path).infer_public_skills() == ["public"]


def test_infer_public_skills_returns_empty_when_no_public_cli_commands_exist(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"
""",
        encoding="utf-8",
    )
    skill = tmp_path / "skills" / "skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Run `uvx sample --help`.", encoding="utf-8")

    assert SkillSearcher(tmp_path).infer_public_skills() == []


@pytest.mark.parametrize(
    ("fence", "command_line"),
    [("```", "sample --help"), ("~~~", "$ sample --help")],
)
def test_infer_public_skills_accepts_declared_command_in_code_block(
    tmp_path: Path, fence: str, command_line: str
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"

[project.scripts]
sample = "sample.cli:main"
""",
        encoding="utf-8",
    )
    skill = tmp_path / "skills" / "skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"{fence}console\n{command_line}\n{fence}", encoding="utf-8")

    assert SkillSearcher(tmp_path).infer_public_skills() == ["skill"]


def test_infer_public_skills_does_not_match_command_mentions_outside_code_blocks_or_partial_names(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"

[project.scripts]
sample = "sample.cli:main"
""",
        encoding="utf-8",
    )
    skill = tmp_path / "skills" / "skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "Run sample in your terminal.\n\n```console\nsample-extra --help\n```",
        encoding="utf-8",
    )

    assert SkillSearcher(tmp_path).infer_public_skills() == []


@pytest.mark.parametrize("runner", ["uvx", "uv tool run"])
def test_infer_public_skills_accepts_uv_cli_invocation_forms(tmp_path: Path, runner: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"

[project.scripts]
sample = "sample.cli:main"
""",
        encoding="utf-8",
    )
    skill = tmp_path / "skills" / "skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"Run `{runner} sample --help`.", encoding="utf-8")

    assert SkillSearcher(tmp_path).infer_public_skills() == ["skill"]


@pytest.mark.parametrize("runner", ["uvx", "uv tool run"])
def test_infer_public_skills_accepts_uv_from_option(tmp_path: Path, runner: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"

[project.scripts]
sample = "sample.cli:main"
""",
        encoding="utf-8",
    )
    skill = tmp_path / "skills" / "skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"Run `{runner} --from ./packages/sample sample --help`.",
        encoding="utf-8",
    )

    assert SkillSearcher(tmp_path).infer_public_skills() == ["skill"]
