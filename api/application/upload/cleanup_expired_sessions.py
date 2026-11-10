from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from api.application.audit import record
from api.data.models import SessionStatus, User
from api.domain import permissions
from api.domain import sessions as session_rules
from api.domain.permissions import Action
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.download_session import (
    DownloadSessionRepository,
)
from api.persistence.repository.upload_session import UploadSessionRepository


@dataclass
class CleanupExpiredSessions:
    """Expire idle sessions and free the pieces of unfinished uploads.

    Attributes:
        uploads: Stores the upload sessions.
        downloads: Stores the download sessions.
        storage: Stores the blobs and the staged pieces.
        audit: Receives the audit events.
        clock: Returns the current moment.
        session_ttl: Maximum inactivity before a session expires.
    """

    uploads: UploadSessionRepository
    downloads: DownloadSessionRepository
    storage: BlobStorage
    audit: AuditLogRepository
    clock: Callable[[], datetime]
    session_ttl: timedelta

    def execute(self, actor: User | None = None) -> int:
        """Expire every open session that has been idle too long.

        Runs as a system job (no actor) or on an admin's request.

        Args:
            actor: Admin making the request, or None for the system.

        Returns:
            Number of sessions expired.

        Raises:
            PermissionDenied: If an actor is given and is not an admin.
        """
        if actor is not None:
            permissions.require(actor.role, Action.ADMINISTER)

        now = self.clock()
        expired = 0

        for kind, repository in (
            ("upload", self.uploads),
            ("download", self.downloads),
        ):
            for session in repository.list_open():
                if not session_rules.is_expired(
                    session.last_activity, now, self.session_ttl
                ):
                    continue

                if kind == "upload":
                    self.storage.discard(session.id)

                session.status = SessionStatus.EXPIRED
                repository.update(session)
                record(self.audit, self.clock, session.user_id, session.id,
                       f"{kind}.expire", "expired")
                expired += 1

        return expired
