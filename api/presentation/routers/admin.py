from fastapi import APIRouter, Depends, Query

from api.data.models import User
from api.presentation.dependencies import current_user, get_services
from api.presentation.schemas import AuditItem, AuditResponse, CleanupResponse
from api.presentation.services import ApiServices


router = APIRouter(tags=["admin"])


@router.get("/audit", response_model=AuditResponse)
def audit_events(
    limit: int = Query(default=100, ge=1, le=1000),
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """List the most recent audit events (admin only).

    Args:
        limit: Maximum number of events, from 1 to 1000.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The events, newest first.
    """
    return AuditResponse(
        events=[
            AuditItem(
                user_id=e.user_id,
                session_id=e.session_id,
                event=e.event,
                result=e.result,
                detail=e.detail,
                created_at=e.created_at,
            )
            for e in services.audit_events.execute(user, limit)
        ]
    )


@router.post("/admin/cleanup", response_model=CleanupResponse)
def cleanup(
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Expire idle sessions now (admin only).

    Args:
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        How many sessions were expired.
    """
    return CleanupResponse(expired=services.cleanup.execute(user))
