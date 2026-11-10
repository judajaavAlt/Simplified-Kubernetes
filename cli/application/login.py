"""``login`` and ``logout`` (C-28, C-29, C-50)."""
from dataclasses import dataclass

from cli.data.models import Credentials
from cli.domain import references
from cli.domain.errors import (
    NotLoggedInError,
    PasswordChangeRequiredError,
    RegistryError,
)
from cli.domain.ports import Prompter, RegistryConnector
from cli.persistence.settings_store import CredentialStore


@dataclass
class Login:
    """Log in to a registry and save the token for that host.

    Attributes:
        credentials: Saved sessions, one per registry.
        connector: Creates registry clients.
        prompter: Asks the new password when the registry requires it.
    """

    credentials: CredentialStore
    connector: RegistryConnector
    prompter: Prompter

    def execute(
        self, registry: str, nickname: str, password: str, insecure: bool = False
    ) -> Credentials:
        """Get a token and save it.

        If the registry requires a password change (first login with a
        temporary password), the new password is asked and set, and the
        login is repeated with it.

        Args:
            registry: ``host:port``.
            nickname: User name.
            password: Password.
            insecure: Use HTTP instead of HTTPS.

        Returns:
            The saved credentials.

        Raises:
            ValidationError: If the registry address is invalid.
            RegistryError: If the registry refuses the credentials.
        """
        references.parse_registry(registry)
        client = self.connector.connect(registry, secure=not insecure)
        try:
            token = client.login(nickname, password)
        except PasswordChangeRequiredError:
            new_password = self.prompter.ask_new_password()
            client.change_password(nickname, password, new_password)
            token = client.login(nickname, new_password)
        credentials = Credentials(registry, token, nickname, not insecure)
        self.credentials.save(credentials)
        return credentials


@dataclass
class Logout:
    """Revoke the token of a registry and forget it.

    Attributes:
        credentials: Saved sessions, one per registry.
        connector: Creates registry clients.
    """

    credentials: CredentialStore
    connector: RegistryConnector

    def execute(self, registry: str) -> bool:
        """Log out of a registry.

        The local token is forgotten even if the registry cannot be reached.

        Args:
            registry: ``host:port``.

        Returns:
            True if the registry revoked the token.

        Raises:
            NotLoggedInError: If there is no session for the registry.
        """
        saved = self.credentials.get(registry)
        if saved is None:
            raise NotLoggedInError(f"Not logged in to {registry}")
        try:
            self.connector.connect(registry, saved.secure, saved.token).logout()
            revoked = True
        except RegistryError:
            revoked = False
        self.credentials.delete(registry)
        return revoked
