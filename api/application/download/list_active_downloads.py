from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from api.data.models import DownloadSession, User
from api.domain import permissions
from api.domain import sessions as session_rules
from api.domain.permissions import Action
from api.persistence.repository.download_session import (
    DownloadSessionRepository,
)


@dataclass
class ListActiveDownloads:
    """Let an admin know whether a download is in progress.

    Attributes:
        sessions: Stores the transfer sessions.
        clock: Returns the current moment.
        session_ttl: Maximum inactivity before a session expires.
    """

    sessions: DownloadSessionRepository
    clock: Callable[[], datetime]
    session_ttl: timedelta

    def execute(self, actor: User) -> list[DownloadSession]:
        """List the open downloads that have not expired.

        Args:
            actor: Admin making the request.

        Returns:
            The active download sessions.

        Raises:
            PermissionDenied: If the actor is not an admin.
        """
        permissions.require(actor.role, Action.ADMINISTER)
        now = self.clock()

        return [
            session
            for session in self.sessions.list_open()
            if not session_rules.is_expired(
                session.last_activity, now, self.session_ttl
            )
        ]
