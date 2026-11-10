from abc import ABC, abstractmethod
from datetime import datetime

from api.data.models import UserToken


class UserTokenRepository(ABC):
    """Port that stores bearer tokens (only their hashes)."""

    @abstractmethod
    def create(self, token: UserToken) -> None:
        """Persist a newly issued token.

        Args:
            token: Token whose ``signature`` is the hash of the raw token.
        """

    @abstractmethod
    def get_by_signature(self, signature: str) -> UserToken | None:
        """Find a token by its stored hash.

        Args:
            signature: SHA-256 of the raw token.

        Returns:
            The token, or None if it does not exist.
        """

    @abstractmethod
    def revoke(self, signature: str, revoked_at: datetime) -> None:
        """Revoke a token.

        Args:
            signature: SHA-256 of the raw token.
            revoked_at: Moment of the revocation.
        """

    @abstractmethod
    def revoke_all_for_user(self, user_id: int, revoked_at: datetime) -> None:
        """Revoke every active token of a user.

        Args:
            user_id: Owner of the tokens.
            revoked_at: Moment of the revocation.
        """
