from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.application.audit import record
from api.application.transfer_sessions import load_owned_open
from api.data.models import SessionStatus, User
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.upload_session import UploadSessionRepository


@dataclass
class CancelUpload:
    """Cancel an upload and discard its received pieces.

    Attributes:
        sessions: Stores the transfer sessions.
        storage: Stores the blobs and the staged pieces.
        audit: Receives the audit events.
        clock: Returns the current moment.
    """

    sessions: UploadSessionRepository
    storage: BlobStorage
    audit: AuditLogRepository
    clock: Callable[[], datetime]

    def execute(self, actor: User, upload_id: str) -> None:
        """Cancel an open upload of the actor.

        Args:
            actor: User that started the upload.
            upload_id: Upload session identifier.

        Raises:
            NotFound: If the session does not exist.
            PermissionDenied: If the session belongs to another user.
            Conflict: If the session is no longer open.
        """
        session = load_owned_open(self.sessions, upload_id, actor)

        self.storage.discard(upload_id)
        session.status = SessionStatus.CANCELLED
        session.last_activity = self.clock()
        self.sessions.update(session)

        record(self.audit, self.clock, actor.id, upload_id,
               "upload.cancel", "cancelled")
