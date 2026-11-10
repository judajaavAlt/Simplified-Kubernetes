from abc import ABC, abstractmethod

from api.data.models import UploadSession


class UploadSessionRepository(ABC):
    """Port that stores upload sessions."""

    @abstractmethod
    def create(self, session: UploadSession) -> None:
        """Persist a new upload session.

        Args:
            session: Session to store.
        """
        pass

    @abstractmethod
    def get(self, session_id: str) -> UploadSession | None:
        """Find an upload session.

        Args:
            session_id: Session identifier.

        Returns:
            The session, or None if it does not exist.
        """
        pass

    @abstractmethod
    def update(self, session: UploadSession) -> None:
        """Persist the status, received pieces and last activity of a session.

        Args:
            session: Session with the new values.
        """

    @abstractmethod
    def list_open(self) -> list[UploadSession]:
        """List the sessions that are still open.

        Returns:
            Every session whose status is ``OPEN``.
        """
        pass
