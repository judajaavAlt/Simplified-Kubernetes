from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from api.application.audit import record
from api.application.transfer_sessions import load_owned_open
from api.data.models import User
from api.domain.errors import InvalidInput, NotFound
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.download_session import (
    DownloadSessionRepository,
)


@dataclass
class DownloadedPiece:
    """One piece handed out to the client.

    Attributes:
        index: Position of the piece, starting at 0.
        signature: SHA-256 of the piece, so the client can verify it.
        content: Bytes of the piece.
    """

    index: int
    signature: str
    content: bytes


@dataclass
class DownloadChunk:
    """Hand out one 1 MB piece with its SHA-256 so the client verifies it.

    Attributes:
        sessions: Stores the transfer sessions.
        storage: Stores the blobs and the staged pieces.
        audit: Receives the audit events.
        clock: Returns the current moment.
        session_ttl: Maximum inactivity before a session expires.
    """

    sessions: DownloadSessionRepository
    storage: BlobStorage
    audit: AuditLogRepository
    clock: Callable[[], datetime]
    session_ttl: timedelta

    def execute(
        self, actor: User, download_id: str, index: int
    ) -> DownloadedPiece:
        """Read one piece of the blob of an open download.

        Args:
            actor: User that started the download.
            download_id: Download session identifier.
            index: Position of the piece, starting at 0.

        Returns:
            The piece with its signature.

        Raises:
            NotFound: If the session or the blob no longer exist.
            InvalidInput: If the index is out of range.
            PermissionDenied: If the session belongs to another user.
            Conflict: If the session is not open or has expired.
        """
        now = self.clock()
        session = load_owned_open(
            self.sessions, download_id, actor, now, self.session_ttl
        )
        metadata = self.storage.read_metadata(session.blob_signature)

        if metadata is None:
            raise NotFound("The blob is no longer stored")

        if index < 0 or index >= len(metadata.pieces):
            raise InvalidInput(f"Piece index out of range: {index}")

        piece = metadata.pieces[index]
        content = self.storage.read_piece(
            session.blob_signature, piece.signature
        )

        session.last_activity = now
        self.sessions.update(session)

        record(self.audit, self.clock, actor.id, download_id,
               "download.chunk", "ok", f"piece {index}")

        return DownloadedPiece(
            index=index, signature=piece.signature, content=content
        )
