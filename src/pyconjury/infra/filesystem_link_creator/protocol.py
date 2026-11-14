from pathlib import Path
from typing import Protocol


class FileSystemLinkCreatorProtocol(Protocol):
    def validate_directory_link(self, source: Path, destination: Path) -> bool:
        """Return True if the destination already links to the source; raise OSError on conflict."""
        ...

    def validate_directory_link_for_removal(self, source: Path, destination: Path) -> bool:
        """Return True if the destination is a removable link to source; raise OSError on conflict."""
        ...

    def create_directory_link(self, source: Path, destination: Path) -> None: ...

    def remove_directory_link(self, source: Path, destination: Path) -> None: ...

    def create_file_link(self, source: Path, destination: Path) -> None: ...
