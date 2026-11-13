import os
from pathlib import Path


def _validate_directory_link(source: Path, destination: Path) -> bool:
    try:
        source = source.resolve(strict=True)
    except OSError as error:
        raise FileNotFoundError(f"Cannot create Skill link because its target is unavailable: {source}") from error

    if not os.path.lexists(destination):
        return False

    is_directory_link = destination.is_symlink() or destination.is_junction()
    if is_directory_link:
        try:
            if destination.resolve(strict=False) == source:
                return True
        except (OSError, RuntimeError):
            pass

    raise FileExistsError(f"Cannot create Skill link because the destination already exists: {destination}")
