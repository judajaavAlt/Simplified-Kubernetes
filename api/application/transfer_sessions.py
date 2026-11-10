from datetime import datetime, timedelta

from api.data.models import SessionStatus, User
from api.domain import sessions as session_rules
from api.domain.errors import Conflict, NotFound, PermissionDenied


def load_owned(repository, session_id: str, actor: User):
    """Load an upload or download session that belongs to the actor.

    Args:
        repository: Upload or download session repository.
        session_id: Session identifier.
        actor: User making the request.

    Returns:
        The session.

    Raises:
        NotFound: If the session does not exist.
        PermissionDenied: If the session belongs to another user.
    """
    session = repository.get(session_id)

    if session is None:
        raise NotFound("Session not found")

    if session.user_id != actor.id:
        raise PermissionDenied("The session belongs to another user")

    return session


def load_owned_open(
    repository,
    session_id: str,
    actor: User,
    now: datetime | None = None,
    ttl: timedelta | None = None,
):
    """Load a session of the actor that is still open and alive.

    Args:
        repository: Upload or download session repository.
        session_id: Session identifier.
        actor: User making the request.
        now: Current moment; required when ``ttl`` is given.
        ttl: Maximum inactivity; None skips the expiration check.

    Returns:
        The session.

    Raises:
        NotFound: If the session does not exist.
        PermissionDenied: If the session belongs to another user.
        Conflict: If the session is not open or has expired.
    """
    session = load_owned(repository, session_id, actor)

    if session.status is not SessionStatus.OPEN:
        raise Conflict(f"The session is {session.status.value}")

    if ttl is not None and session_rules.is_expired(
        session.last_activity, now, ttl
    ):
        raise Conflict("The session expired")

    return session
