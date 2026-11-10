from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from api.application.audit import record
from api.application.transfer_sessions import load_owned_open
from api.data.models import User
from api.domain import checksum, chunking
from api.domain.errors import ChecksumMismatch, InvalidInput
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.upload_session import UploadSessionRepository


@dataclass
class UploadChunk:
    """Receive one 1 MB piece, verify its own SHA-256 and log it.

    Attributes:
        sessions: Stores the transfer sessions.
        storage: Stores the blobs and the staged pieces.
        audit: Receives the audit events.
        clock: Returns the current moment.
        session_ttl: Maximum inactivity before a session expires.
    """

    sessions: UploadSessionRepository
    storage: BlobStorage
    audit: AuditLogRepository
    clock: Callable[[], datetime]
    session_ttl: timedelta

    def execute(
        self,
        actor: User,
        upload_id: str,
        index: int,
        signature: str,
        content: bytes,
    ) -> None:
        """Store one piece of an open upload.

        Sending the same piece again is harmless.

        Args:
            actor: User that started the upload.
            upload_id: Upload session identifier.
            index: Position of the piece, starting at 0.
            signature: SHA-256 of the piece.
            content: Bytes of the piece.

        Raises:
            InvalidInput: If the index is out of range or the size is wrong.
            ChecksumMismatch: If the content does not match ``signature``.
            NotFound: If the session does not exist.
            PermissionDenied: If the session belongs to another user.
            Conflict: If the session is not open or has expired.
        """
        now = self.clock()
        session = load_owned_open(
            self.sessions, upload_id, actor, now, self.session_ttl
        )

        expected_size = chunking.piece_size(session.total_size, index)

        if len(content) != expected_size:
            raise InvalidInput(
                f"Piece {index} must have {expected_size} bytes"
            )

        if not checksum.is_sha256_hex(signature) or not checksum.matches(
            content, signature
        ):
            record(self.audit, self.clock, actor.id, upload_id,
                   "upload.chunk", "rejected", f"piece {index}")
            raise ChecksumMismatch(f"Piece {index} checksum mismatch")

        # Sending the same piece again is harmless.
        if session.received.get(index) != signature:
            self.storage.save_temp_piece(upload_id, signature, content)
            session.received[index] = signature

        session.last_activity = now
        self.sessions.update(session)

        record(self.audit, self.clock, actor.id, upload_id,
               "upload.chunk", "ok", f"piece {index}")
