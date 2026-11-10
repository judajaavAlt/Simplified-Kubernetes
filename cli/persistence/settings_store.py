from abc import ABC, abstractmethod

from cli.data.models import Credentials


class SettingsStore(ABC):
    """Port to the CLI settings (``config.json``)."""

    @abstractmethod
    def get_prefix(self) -> str | None:
        """Read the default prefix set with ``work set``.

        Returns:
            The prefix, or None if none was set.
        """

    @abstractmethod
    def set_prefix(self, prefix: str | None) -> None:
        """Save the default prefix.

        Args:
            prefix: ``host:port[/org[/repo]]``, or None to remove it.
        """


class CredentialStore(ABC):
    """Port to the registry sessions (``credentials.json``), one per host."""

    @abstractmethod
    def get(self, registry: str) -> Credentials | None:
        """Find the session of a registry.

        Args:
            registry: ``host:port``.

        Returns:
            The credentials, or None if not logged in.
        """

    @abstractmethod
    def save(self, credentials: Credentials) -> None:
        """Save or replace the session of a registry.

        Args:
            credentials: Credentials to save.
        """

    @abstractmethod
    def delete(self, registry: str) -> None:
        """Forget the session of a registry.

        Args:
            registry: ``host:port``.
        """
