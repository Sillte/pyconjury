import sys

from .protocol import FileSystemLinkCreatorProtocol


def create_default_file_system_link_creator() -> FileSystemLinkCreatorProtocol:
    if sys.platform == "win32":
        from .impls.windows import WindowsFileSystemLinkCreator

        return WindowsFileSystemLinkCreator()

    from .impls.linux import LinuxFileSystemLinkCreator

    return LinuxFileSystemLinkCreator()


__all__ = ["FileSystemLinkCreatorProtocol", "create_default_file_system_link_creator"]
