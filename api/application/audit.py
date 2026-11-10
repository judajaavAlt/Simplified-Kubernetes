from collections.abc import Callable
from datetime import datetime

from api.data.models import AuditEvent
from api.persistence.repository.audit_log import AuditLogRepository


def record(
    audit: AuditLogRepository,
    clock: Callable[[], datetime],
    user_id: int,
    session_id: str | None,
    event: str,
    result: str,
    detail: str = "",
) -> None:
    """Append one entry to the audit log (who, when, what and result).

    Args:
        audit: Audit log that receives the entry.
        clock: Returns the moment of the entry.
        user_id: User that performed the action.
        session_id: Related transfer session, if any.
        event: Name of the action, for example ``upload.chunk``.
        result: Outcome of the action.
        detail: Free text with extra information.
    """
    audit.add(
        AuditEvent(
            user_id=user_id,
            session_id=session_id,
            event=event,
            result=result,
            created_at=clock(),
            detail=detail,
        )
    )
