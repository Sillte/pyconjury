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
