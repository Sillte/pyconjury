import os
from pathlib import Path

import pytest

from pyconjury.infra.filesystem_link_creator import create_default_file_system_link_creator


def test_create_directory_link_is_idempotent_for_the_same_target(tmp_path: Path) -> None:
    target = tmp_path / "source"
    target.mkdir()
    link = tmp_path / ".agents" / "skills" / "source"
    link_creator = create_default_file_system_link_creator()

    link_creator.create_directory_link(target, link)
    link_creator.create_directory_link(target, link)

    assert link.is_dir()
    if os.name == "nt":
        assert link.is_junction()
    else:
        assert link.is_symlink()


def test_create_directory_link_does_not_replace_an_existing_path(tmp_path: Path) -> None:
    target = tmp_path / "source"
    target.mkdir()
    link = tmp_path / ".agents" / "skills" / "source"
    link.mkdir(parents=True)
    link_creator = create_default_file_system_link_creator()

    with pytest.raises(FileExistsError, match="destination already exists"):
        link_creator.create_directory_link(target, link)

    assert link.is_dir()
    assert not link.is_symlink()


def test_remove_directory_link_removes_only_the_link(tmp_path: Path) -> None:
    target = tmp_path / "source"
    target.mkdir()
    link = tmp_path / ".agents" / "skills" / "source"
    link_creator = create_default_file_system_link_creator()
    link_creator.create_directory_link(target, link)

    assert link_creator.validate_directory_link_for_removal(target, link)
    link_creator.remove_directory_link(target, link)

    assert target.is_dir()
    assert not os.path.lexists(link)


def test_remove_directory_link_preserves_an_existing_directory(tmp_path: Path) -> None:
    target = tmp_path / "source"
    target.mkdir()
    link = tmp_path / ".agents" / "skills" / "source"
    link.mkdir(parents=True)
    link_creator = create_default_file_system_link_creator()

    with pytest.raises(FileExistsError, match="not a directory link"):
        link_creator.remove_directory_link(target, link)

    assert link.is_dir()


def test_remove_directory_link_preserves_a_link_to_another_target(tmp_path: Path) -> None:
    target = tmp_path / "source"
    other_target = tmp_path / "other-source"
    target.mkdir()
    other_target.mkdir()
    link = tmp_path / ".agents" / "skills" / "source"
    link_creator = create_default_file_system_link_creator()
    link_creator.create_directory_link(other_target, link)

    with pytest.raises(FileExistsError, match="points elsewhere"):
        link_creator.remove_directory_link(target, link)

    assert link.is_dir()
    assert link.resolve() == other_target.resolve()


def test_remove_directory_link_can_remove_a_link_after_its_target_is_gone(tmp_path: Path) -> None:
    target = tmp_path / "source"
    target.mkdir()
    link = tmp_path / ".agents" / "skills" / "source"
    link_creator = create_default_file_system_link_creator()
    link_creator.create_directory_link(target, link)
    target.rmdir()

    link_creator.remove_directory_link(target, link)

    assert not os.path.lexists(link)
