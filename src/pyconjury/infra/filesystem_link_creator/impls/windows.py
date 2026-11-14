import os
import subprocess
from pathlib import Path

from pyconjury.infra.filesystem_link_creator.protocol import FileSystemLinkCreatorProtocol
from pyconjury.infra.filesystem_link_creator.shared import (
    _validate_directory_link,
    _validate_directory_link_for_removal,
)


class WindowsFileSystemLinkCreator(FileSystemLinkCreatorProtocol):
    def create_directory_link(self, source: Path, destination: Path) -> None:
        if self.validate_directory_link(source, destination):
            return
        source = source.resolve(strict=True)
        if "%" in str(source) or "%" in str(destination):
            raise OSError("Cannot create a Windows junction for a path containing '%'.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        command = f'mklink /J "{destination}" "{source}"'
        try:
            subprocess.run(
                command,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as error:
            raise OSError("Command Prompt is required to create Skill junctions on Windows.") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip()
            raise OSError(f"Cannot create Skill junction {destination}: {detail or 'mklink failed.'}") from error

    def validate_directory_link(self, source: Path, destination: Path) -> bool:
        return _validate_directory_link(source, destination)

    def validate_directory_link_for_removal(self, source: Path, destination: Path) -> bool:
        return _validate_directory_link_for_removal(source, destination)

    def remove_directory_link(self, source: Path, destination: Path) -> None:
        if not self.validate_directory_link_for_removal(source, destination):
            return
        if destination.is_junction():
            os.rmdir(destination)
        else:
            destination.unlink()

    def create_file_link(self, source: Path, destination: Path) -> None:
        destination.symlink_to(source.resolve(strict=True))
