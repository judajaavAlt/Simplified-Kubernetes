import shutil
from pathlib import Path

from cli.domain.errors import NotFoundError
from cli.persistence.file_system import FileSystem


class LocalFileSystem(FileSystem):
    """The real file system, through ``pathlib`` and ``shutil``."""

    def exists(self, path: Path) -> bool:
        """Check whether a file or folder exists.

        Args:
            path: Path to check.

        Returns:
            True if it exists.
        """
        return Path(path).exists()

    def is_dir(self, path: Path) -> bool:
        """Check whether a path is a folder.

        Args:
            path: Path to check.

        Returns:
            True if it is an existing folder.
        """
        return Path(path).is_dir()

    def list_dir(self, path: Path) -> list[str]:
        """List the names inside a folder.

        Args:
            path: Folder to list.

        Returns:
            The names, sorted.
        """
        return sorted(child.name for child in Path(path).iterdir())

    def read_bytes(self, path: Path) -> bytes:
        """Read a file.

        Args:
            path: File to read.

        Returns:
            Its bytes.

        Raises:
            NotFoundError: If the file does not exist.
        """
        try:
            return Path(path).read_bytes()
        except FileNotFoundError:
            raise NotFoundError(f"File not found: {path}") from None

    def write_bytes(self, path: Path, content: bytes) -> None:
        """Write a file, creating its folders.

        Args:
            path: File to write.
            content: Bytes to write.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def make_dirs(self, path: Path) -> None:
        """Create a folder and its parents.

        Args:
            path: Folder to create.
        """
        Path(path).mkdir(parents=True, exist_ok=True)

    def remove(self, path: Path) -> None:
        """Delete a file or a whole folder; a missing path is fine.

        Args:
            path: Path to delete.
        """
        path = Path(path)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()

    def copy(self, source: Path, target: Path) -> None:
        """Copy a file or a whole folder.

        Args:
            source: Path to copy.
            target: Destination path.

        Raises:
            NotFoundError: If the source does not exist.
        """
        source, target = Path(source), Path(target)
        if not source.exists():
            raise NotFoundError(f"Path not found: {source}")
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def move(self, source: Path, target: Path) -> None:
        """Move or rename a file or folder.

        Args:
            source: Path to move.
            target: Destination path.

        Raises:
            NotFoundError: If the source does not exist.
        """
        source, target = Path(source), Path(target)
        if not source.exists():
            raise NotFoundError(f"Path not found: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
