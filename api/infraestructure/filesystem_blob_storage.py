import json
import os
import re
import shutil
from dataclasses import asdict
from pathlib import Path

from api.data.models import BlobMetadata, PieceInfo
from api.persistence.blob_storage import BlobStorage


# Only plain names: no separators, no "." or "..".
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*$")
_METADATA = "metadata.json"


def _safe(name: str) -> str:
    """Ensure a name can be used as a single file or folder name.

    Args:
        name: Session identifier or signature.

    Returns:
        The same name.

    Raises:
        ValueError: If the name has separators or is ``.`` or ``..``.
    """
    if not _SAFE_NAME.match(name) or name in {".", ".."}:
        raise ValueError(f"Unsafe storage name: {name!r}")

    return name


class FileSystemBlobStorage(BlobStorage):
    """Blob storage on the local filesystem.

    Layout::

        <root>/uploads/<session_id>/<piece_sha>   pieces of unfinished uploads
        <root>/blobs/<blob_sha>/<piece_sha>       1 MB pieces of a blob
        <root>/blobs/<blob_sha>/metadata.json     order and size of the pieces

    Attributes:
        uploads: Folder with the staged pieces.
        blobs: Folder with the committed blobs.
    """

    def __init__(self, root: Path):
        """Create the storage.

        Args:
            root: Base folder; created on the first write.
        """
        self.uploads = Path(root) / "uploads"
        self.blobs = Path(root) / "blobs"

    # Upload staging ---------------------------------------------------

    def save_temp_piece(
        self, session_id: str, signature: str, content: bytes
    ) -> None:
        """Keep a received piece until the upload is finished.

        Args:
            session_id: Upload session that received the piece.
            signature: SHA-256 of the piece.
            content: Bytes of the piece.
        """
        folder = self.uploads / _safe(session_id)
        folder.mkdir(parents=True, exist_ok=True)
        _write_atomic(folder / _safe(signature), content)

    def read_temp_piece(self, session_id: str, signature: str) -> bytes:
        """Read a staged piece of an unfinished upload.

        Args:
            session_id: Upload session that received the piece.
            signature: SHA-256 of the piece.

        Returns:
            Bytes of the piece.
        """
        return (self.uploads / _safe(session_id) / _safe(signature)).read_bytes()

    def commit(self, session_id: str, metadata: BlobMetadata) -> None:
        """Move the staged pieces to the blob folder and write its metadata.

        Args:
            session_id: Upload session whose pieces are committed.
            metadata: Signature, size and ordered pieces of the blob.
        """
        source = self.uploads / _safe(session_id)
        target = self.blobs / _safe(metadata.signature)
        staging = self.blobs / f"{target.name}.partial"

        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)

        for piece in metadata.pieces:
            name = _safe(piece.signature)
            destination = staging / name

            if not destination.exists():  # identical pieces are stored once
                shutil.copyfile(source / name, destination)

        (staging / _METADATA).write_text(
            json.dumps(asdict(metadata), indent=2), encoding="utf-8"
        )

        # The blob only becomes visible when it is complete.
        os.replace(staging, target)
        shutil.rmtree(source, ignore_errors=True)

    def discard(self, session_id: str) -> None:
        """Delete every staged piece of an upload.

        Args:
            session_id: Upload session to clean.
        """
        shutil.rmtree(self.uploads / _safe(session_id), ignore_errors=True)

    # Committed blobs --------------------------------------------------

    def exists(self, signature: str) -> bool:
        """Check whether a blob is committed.

        Args:
            signature: SHA-256 of the blob.

        Returns:
            True if the blob is stored.
        """
        return (self.blobs / _safe(signature) / _METADATA).is_file()

    def read_metadata(self, signature: str) -> BlobMetadata | None:
        """Read the metadata of a committed blob.

        Args:
            signature: SHA-256 of the blob.

        Returns:
            The metadata, or None if the blob does not exist.
        """
        path = self.blobs / _safe(signature) / _METADATA

        if not path.is_file():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))

        return BlobMetadata(
            signature=data["signature"],
            total_size=data["total_size"],
            chunk_size=data["chunk_size"],
            pieces=[PieceInfo(**piece) for piece in data["pieces"]],
        )

    def read_piece(self, signature: str, piece_signature: str) -> bytes:
        """Read one piece of a committed blob.

        Args:
            signature: SHA-256 of the blob.
            piece_signature: SHA-256 of the piece.

        Returns:
            Bytes of the piece.
        """
        return (
            self.blobs / _safe(signature) / _safe(piece_signature)
        ).read_bytes()

    def delete(self, signature: str) -> None:
        """Delete a committed blob and all its pieces.

        Args:
            signature: SHA-256 of the blob.
        """
        shutil.rmtree(self.blobs / _safe(signature), ignore_errors=True)


def _write_atomic(path: Path, content: bytes) -> None:
    """Write a file so that it is either complete or absent.

    Args:
        path: Destination file.
        content: Bytes to write.
    """
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
