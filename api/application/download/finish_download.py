from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.application.audit import record
from api.application.transfer_sessions import load_owned_open
from api.data.models import SessionStatus, User
from api.domain import checksum
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.download_session import (
    DownloadSessionRepository,
)


@dataclass
class FinishDownload:
    """Record the SHA-256 the client rebuilt and close the download.

    Attributes:
        sessions: Stores the transfer sessions.
        audit: Receives the audit events.
        clock: Returns the current moment.
    """

    sessions: DownloadSessionRepository
    audit: AuditLogRepository
    clock: Callable[[], datetime]

    def execute(self, actor: User, download_id: str, signature: str) -> bool:
        """Close a download as completed or failed.

        Args:
            actor: User that started the download.
            download_id: Download session identifier.
            signature: SHA-256 of the blob rebuilt by the client.

        Returns:
            True if the signature matches the blob.

        Raises:
            NotFound: If the session does not exist.
            PermissionDenied: If the session belongs to another user.
            Conflict: If the session is no longer open.
        """
        session = load_owned_open(self.sessions, download_id, actor)

        ok = checksum.is_sha256_hex(signature) and checksum.same_signature(
            signature, session.blob_signature
        )

        session.status = (
            SessionStatus.COMPLETED if ok else SessionStatus.FAILED
        )
        session.last_activity = self.clock()
        self.sessions.update(session)

        record(self.audit, self.clock, actor.id, download_id,
               "download.finish", session.status.value)

        return ok
