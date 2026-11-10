from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.data.models import User
from api.domain import tokens as token_rules
from api.domain.errors import AuthenticationError, PasswordChangeRequired
from api.persistence.repository.user import UserRepository
from api.persistence.repository.user_token import UserTokenRepository


@dataclass
class ValidateToken:
    """Find the user behind a bearer token.

    Attributes:
        tokens: Stores the token hashes.
        users: Stores the users.
        clock: Returns the current moment.
    """

    tokens: UserTokenRepository
    users: UserRepository
    clock: Callable[[], datetime]

    def execute(self, raw_token: str) -> User:
        """Return the owner of a valid token.

        Args:
            raw_token: Token as sent by the client.

        Returns:
            The user that owns the token.

        Raises:
            AuthenticationError: If the token is unknown, revoked or expired,
                or its user no longer exists.
            PasswordChangeRequired: If the user must change the password.
        """
        token = self.tokens.get_by_signature(
            token_rules.signature_of(raw_token)
        )

        if token is None or not token_rules.is_active(token, self.clock()):
            raise AuthenticationError("Invalid token")

        user = self.users.get_by_id(token.user_id)

        if user is None:
            raise AuthenticationError("Invalid token")

        if user.must_change_password:
            raise PasswordChangeRequired("The password must be changed")

        return user
