from pathlib import Path
from typing import Protocol


class FileSystemLinkCreatorProtocol(Protocol):
    def validate_directory_link(self, source: Path, destination: Path) -> bool:
        """Return True if the destination already links to the source; raise OSError on conflict."""
        ...

    def create_directory_link(self, source: Path, destination: Path) -> None: ...

    def create_file_link(self, source: Path, destination: Path) -> None: ...
