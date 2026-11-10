"""Clients for the registries the user is logged in to (C-28, C-50)."""
from dataclasses import dataclass

from cli.domain.errors import NotLoggedInError
from cli.domain.ports import RegistryClient, RegistryConnector
from cli.persistence.settings_store import CredentialStore


@dataclass
class RegistrySessions:
    """Creates authenticated clients from the saved credentials.

    Attributes:
        credentials: Saved sessions, one per registry.
        connector: Creates registry clients.
    """

    credentials: CredentialStore
    connector: RegistryConnector

    def client(self, registry: str) -> RegistryClient:
        """Create a client with the saved token of a registry.

        Args:
            registry: ``host:port``.

        Returns:
            The authenticated client.

        Raises:
            NotLoggedInError: If there is no session for the registry.
        """
        credentials = self.credentials.get(registry)
        if credentials is None:
            raise NotLoggedInError(
                f"Not logged in to {registry}; run 'easyk8s login {registry}'"
            )
        return self.connector.connect(
            registry, credentials.secure, credentials.token
        )
