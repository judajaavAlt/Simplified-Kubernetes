from abc import ABC, abstractmethod

from api.data.models import DownloadSession


class DownloadSessionRepository(ABC):
    """Port that stores download sessions."""

    @abstractmethod
    def create(self, session: DownloadSession) -> None:
        """Persist a new download session.

        Args:
            session: Session to store.
        """
        pass

    @abstractmethod
    def get(self, session_id: str) -> DownloadSession | None:
        """Find a download session.

        Args:
            session_id: Session identifier.

        Returns:
            The session, or None if it does not exist.
        """
        pass

    @abstractmethod
    def update(self, session: DownloadSession) -> None:
        """Persist the status and last activity of a session.

        Args:
            session: Session with the new values.
        """
        pass

    @abstractmethod
    def list_open(self) -> list[DownloadSession]:
        """List the sessions that are still open.

        Returns:
            Every session whose status is ``OPEN``.
        """
        pass
