from datetime import datetime, timedelta


def is_expired(
    last_activity: datetime,
    now: datetime,
    ttl: timedelta,
) -> bool:
    """Check whether a session has been inactive for too long.

    Args:
        last_activity: Moment of the last request of the session.
        now: Current moment.
        ttl: Maximum allowed inactivity.

    Returns:
        True if at least ``ttl`` has passed since ``last_activity``.
    """
    return now - last_activity >= ttl
