from abc import ABC, abstractmethod
from datetime import datetime


class BlobStore(ABC):
    """Port that stores manifests or layers by their SHA-256."""

    @abstractmethod
    def save(self, blob_id: str, content: bytes) -> None:
        """Store a blob.

        Args:
            blob_id: SHA-256 of the content.
            content: Bytes to store.
        """

    @abstractmethod
    def read(self, blob_id: str) -> bytes:
        """Read a blob.

        Args:
            blob_id: SHA-256 of the content.

        Returns:
            The stored bytes.

        Raises:
            NotFoundError: If the blob is not stored.
        """

    @abstractmethod
    def exists(self, blob_id: str) -> bool:
        """Check whether a blob is stored.

        Args:
            blob_id: SHA-256 of the content.

        Returns:
            True if it is stored.
        """

    @abstractmethod
    def delete(self, blob_id: str) -> None:
        """Delete a blob; a missing blob is fine.

        Args:
            blob_id: SHA-256 of the content.
        """

    @abstractmethod
    def list(self) -> list[tuple[str, datetime]]:
        """List the stored blobs.

        Returns:
            Each ID with the moment it was stored.
        """
