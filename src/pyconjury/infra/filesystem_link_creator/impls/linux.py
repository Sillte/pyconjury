from pathlib import Path

from pyconjury.infra.filesystem_link_creator.protocol import FileSystemLinkCreatorProtocol
from pyconjury.infra.filesystem_link_creator.shared import (
    _validate_directory_link,
    _validate_directory_link_for_removal,
)


class LinuxFileSystemLinkCreator(FileSystemLinkCreatorProtocol):
    def validate_directory_link(self, source: Path, destination: Path) -> bool:
        return _validate_directory_link(source, destination)

    def validate_directory_link_for_removal(self, source: Path, destination: Path) -> bool:
        return _validate_directory_link_for_removal(source, destination)

    def create_directory_link(self, source: Path, destination: Path) -> None:
        if self.validate_directory_link(source, destination):
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(source.resolve(strict=True), target_is_directory=True)

    def remove_directory_link(self, source: Path, destination: Path) -> None:
        if self.validate_directory_link_for_removal(source, destination):
            destination.unlink()

    def create_file_link(self, source: Path, destination: Path) -> None:
        destination.symlink_to(source.resolve(strict=True))
