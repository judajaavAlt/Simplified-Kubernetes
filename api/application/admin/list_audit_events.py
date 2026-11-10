from dataclasses import dataclass

from api.data.models import AuditEvent, User
from api.domain import permissions
from api.domain.permissions import Action
from api.persistence.repository.audit_log import AuditLogRepository


@dataclass
class ListAuditEvents:
    """Let an admin read the audit log.

    Attributes:
        audit: Receives the audit events.
    """

    audit: AuditLogRepository

    def execute(self, actor: User, limit: int = 100) -> list[AuditEvent]:
        """List the most recent audit events.

        Args:
            actor: Admin making the request.
            limit: Maximum number of events.

        Returns:
            The events, newest first.

        Raises:
            PermissionDenied: If the actor is not an admin.
        """
        permissions.require(actor.role, Action.ADMINISTER)

        return self.audit.list_recent(limit)
