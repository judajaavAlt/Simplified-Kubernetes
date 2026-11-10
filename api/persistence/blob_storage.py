from abc import ABC, abstractmethod

from api.data.models import BlobMetadata


class BlobStorage(ABC):
    """Port for content addressed storage of blobs (layers and manifests).

    A committed blob lives in a folder named by its SHA-256, with one file
    per 1 MB piece named by the piece SHA-256 and a metadata file that
    records the order of the pieces. Pieces of an unfinished upload are
    staged per session until :meth:`commit` or :meth:`discard`.
    """

    # Upload staging ---------------------------------------------------

    @abstractmethod
    def save_temp_piece(
        self, session_id: str, signature: str, content: bytes
    ) -> None:
        """Keep a received piece until the upload is finished.

        Args:
            session_id: Upload session that received the piece.
            signature: SHA-256 of the piece.
            content: Bytes of the piece.
        """

    @abstractmethod
    def read_temp_piece(self, session_id: str, signature: str) -> bytes:
        """Read a staged piece of an unfinished upload.

        Args:
            session_id: Upload session that received the piece.
            signature: SHA-256 of the piece.

        Returns:
            Bytes of the piece.
        """
        pass

    @abstractmethod
    def commit(self, session_id: str, metadata: BlobMetadata) -> None:
        """Move the staged pieces to the blob folder and write its metadata.

        Args:
            session_id: Upload session whose pieces are committed.
            metadata: Signature, size and ordered pieces of the blob.
        """

    @abstractmethod
    def discard(self, session_id: str) -> None:
        """Delete every staged piece of an upload.

        Args:
            session_id: Upload session to clean.
        """

    # Committed blobs --------------------------------------------------

    @abstractmethod
    def exists(self, signature: str) -> bool:
        """Check whether a blob is committed.

        Args:
            signature: SHA-256 of the blob.

        Returns:
            True if the blob is stored.
        """
        pass

    @abstractmethod
    def read_metadata(self, signature: str) -> BlobMetadata | None:
        """Read the metadata of a committed blob.

        Args:
            signature: SHA-256 of the blob.

        Returns:
            The metadata, or None if the blob does not exist.
        """
        pass

    @abstractmethod
    def read_piece(self, signature: str, piece_signature: str) -> bytes:
        """Read one piece of a committed blob.

        Args:
            signature: SHA-256 of the blob.
            piece_signature: SHA-256 of the piece.

        Returns:
            Bytes of the piece.
        """
        pass

    @abstractmethod
    def delete(self, signature: str) -> None:
        """Delete a committed blob and all its pieces.

        Args:
            signature: SHA-256 of the blob.
        """
        pass
