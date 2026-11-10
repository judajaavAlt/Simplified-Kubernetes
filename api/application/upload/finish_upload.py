from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from api.application.audit import record
from api.application.transfer_sessions import load_owned_open
from api.application.upload.registration import register_blob
from api.data.models import BlobMetadata, PieceInfo, SessionStatus, User
from api.domain import checksum, chunking
from api.domain.errors import ChecksumMismatch, InvalidInput
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.layer import LayerRepository
from api.persistence.repository.manifest import ManifestRepository
from api.persistence.repository.upload_session import UploadSessionRepository


@dataclass
class FinishUpload:
    """Verify the whole blob once and store it if everything went right.

    Attributes:
        sessions: Stores the transfer sessions.
        storage: Stores the blobs and the staged pieces.
        layers: Registers the layers of each repository.
        manifests: Registers the manifests of each repository.
        audit: Receives the audit events.
        clock: Returns the current moment.
        session_ttl: Maximum inactivity before a session expires.
    """

    sessions: UploadSessionRepository
    storage: BlobStorage
    layers: LayerRepository
    manifests: ManifestRepository
    audit: AuditLogRepository
    clock: Callable[[], datetime]
    session_ttl: timedelta

    def execute(self, actor: User, upload_id: str) -> str:
        """Close an upload: check the pieces, verify the blob and commit it.

        Args:
            actor: User that started the upload.
            upload_id: Upload session identifier.

        Returns:
            SHA-256 of the stored blob.

        Raises:
            InvalidInput: If some pieces are missing.
            ChecksumMismatch: If the blob does not match its declared
                SHA-256; the session is marked as failed.
            NotFound: If the session does not exist.
            PermissionDenied: If the session belongs to another user.
            Conflict: If the session is not open or has expired.
        """
        now = self.clock()
        session = load_owned_open(
            self.sessions, upload_id, actor, now, self.session_ttl
        )
        count = chunking.piece_count(session.total_size)
        missing = [i for i in range(count) if i not in session.received]

        if missing:
            raise InvalidInput(f"Missing pieces: {missing}")

        actual = checksum.sha256_of_parts(
            self.storage.read_temp_piece(upload_id, session.received[i])
            for i in range(count)
        )

        if not checksum.same_signature(actual, session.blob_signature):
            self.storage.discard(upload_id)
            self._close(session, SessionStatus.FAILED, now)
            record(self.audit, self.clock, actor.id, upload_id,
                   "upload.finish", "failed", "blob checksum mismatch")
            raise ChecksumMismatch("The blob does not match its signature")

        metadata = BlobMetadata(
            signature=session.blob_signature,
            total_size=session.total_size,
            chunk_size=chunking.CHUNK_SIZE,
            pieces=[
                PieceInfo(
                    index=i,
                    signature=session.received[i],
                    size=chunking.piece_size(session.total_size, i),
                )
                for i in range(count)
            ],
        )

        # Another upload of the same blob may have finished first.
        if self.storage.exists(metadata.signature):
            self.storage.discard(upload_id)
        else:
            self.storage.commit(upload_id, metadata)

        register_blob(
            self.layers,
            self.manifests,
            session.kind,
            session.blob_signature,
            session.repo_id,
            session.layers,
        )
        self._close(session, SessionStatus.COMPLETED, now)

        record(self.audit, self.clock, actor.id, upload_id,
               "upload.finish", "completed", session.blob_signature)

        return session.blob_signature

    def _close(self, session, status: SessionStatus, now: datetime) -> None:
        """Persist the final status of a session.

        Args:
            session: Session to close.
            status: Final status.
            now: Moment of the change.
        """
        session.status = status
        session.last_activity = now
        self.sessions.update(session)
