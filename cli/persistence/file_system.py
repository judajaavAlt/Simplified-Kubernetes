from abc import ABC, abstractmethod
from pathlib import Path


class FileSystem(ABC):
    """Port to the user's files (templates, projects and outputs)."""

    @abstractmethod
    def exists(self, path: Path) -> bool:
        """Check whether a file or folder exists.

        Args:
            path: Path to check.

        Returns:
            True if it exists.
        """

    @abstractmethod
    def is_dir(self, path: Path) -> bool:
        """Check whether a path is a folder.

        Args:
            path: Path to check.

        Returns:
            True if it is an existing folder.
        """

    @abstractmethod
    def list_dir(self, path: Path) -> list[str]:
        """List the names inside a folder.

        Args:
            path: Folder to list.

        Returns:
            The names, sorted.
        """

    @abstractmethod
    def read_bytes(self, path: Path) -> bytes:
        """Read a file.

        Args:
            path: File to read.

        Returns:
            Its bytes.

        Raises:
            NotFoundError: If the file does not exist.
        """

    @abstractmethod
    def write_bytes(self, path: Path, content: bytes) -> None:
        """Write a file, creating its folders.

        Args:
            path: File to write.
            content: Bytes to write.
        """

    @abstractmethod
    def make_dirs(self, path: Path) -> None:
        """Create a folder and its parents; existing folders are fine.

        Args:
            path: Folder to create.
        """

    @abstractmethod
    def remove(self, path: Path) -> None:
        """Delete a file or a whole folder; a missing path is fine.

        Args:
            path: Path to delete.
        """

    @abstractmethod
    def copy(self, source: Path, target: Path) -> None:
        """Copy a file or a whole folder.

        Args:
            source: Path to copy.
            target: Destination path.

        Raises:
            NotFoundError: If the source does not exist.
        """

    @abstractmethod
    def move(self, source: Path, target: Path) -> None:
        """Move or rename a file or folder.

        Args:
            source: Path to move.
            target: Destination path.

        Raises:
            NotFoundError: If the source does not exist.
        """
