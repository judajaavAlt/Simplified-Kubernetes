import os
import re
from datetime import datetime, timezone
from pathlib import Path

from cli.domain.errors import NotFoundError
from cli.persistence.blob_store import BlobStore


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class FileBlobStore(BlobStore):
    """Blobs stored as ``<root>/<id><suffix>`` files.

    Attributes:
        root: Folder of the blobs.
        suffix: File extension, for example ``.yaml`` for manifests.
    """

    def __init__(self, root: Path, suffix: str = ""):
        """Create the store; the folder is created on the first save.

        Args:
            root: Folder of the blobs.
            suffix: File extension.
        """
        self.root = Path(root)
        self.suffix = suffix

    def _path(self, blob_id: str) -> Path:
        """Build the path of a blob.

        Args:
            blob_id: ID of the blob.

        Returns:
            Its file path.

        Raises:
            ValueError: If the ID could escape the folder.
        """
        if not _SAFE_ID.match(blob_id):
            raise ValueError(f"Unsafe blob id: {blob_id!r}")
        return self.root / f"{blob_id}{self.suffix}"

    def save(self, blob_id: str, content: bytes) -> None:
        """Store a blob atomically.

        Args:
            blob_id: SHA-256 of the content.
            content: Bytes to store.
        """
        path = self._path(blob_id)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(content)
        os.replace(temporary, path)

    def read(self, blob_id: str) -> bytes:
        """Read a blob.

        Args:
            blob_id: SHA-256 of the content.

        Returns:
            The stored bytes.

        Raises:
            NotFoundError: If the blob is not stored.
        """
        try:
            return self._path(blob_id).read_bytes()
        except FileNotFoundError:
            raise NotFoundError(f"Blob not found: {blob_id}") from None

    def exists(self, blob_id: str) -> bool:
        """Check whether a blob is stored.

        Args:
            blob_id: SHA-256 of the content.

        Returns:
            True if it is stored.
        """
        return self._path(blob_id).is_file()

    def delete(self, blob_id: str) -> None:
        """Delete a blob; a missing blob is fine.

        Args:
            blob_id: SHA-256 of the content.
        """
        self._path(blob_id).unlink(missing_ok=True)

    def list(self) -> list[tuple[str, datetime]]:
        """List the stored blobs.

        Returns:
            Each ID with its modification moment, in UTC.
        """
        if not self.root.is_dir():
            return []
        result = []
        for path in self.root.iterdir():
            if not path.is_file() or not path.name.endswith(self.suffix):
                continue
            blob_id = path.name[: len(path.name) - len(self.suffix)]
            if _SAFE_ID.match(blob_id):
                moment = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                result.append((blob_id, moment))
        return result
