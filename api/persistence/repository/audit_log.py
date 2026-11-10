from abc import ABC, abstractmethod

from api.data.models import AuditEvent


class AuditLogRepository(ABC):
    """Port that stores the audit log."""

    @abstractmethod
    def add(self, event: AuditEvent) -> None:
        """Append an event to the log.

        Args:
            event: Event to store.
        """
        pass

    @abstractmethod
    def list_recent(self, limit: int = 100) -> list[AuditEvent]:
        """List the most recent events.

        Args:
            limit: Maximum number of events to return.

        Returns:
            The events, newest first.
        """
