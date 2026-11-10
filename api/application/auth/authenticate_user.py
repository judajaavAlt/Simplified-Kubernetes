from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import secrets

from api.data.models import UserToken
from api.domain import tokens as token_rules
from api.domain.errors import AuthenticationError, PasswordChangeRequired
from api.domain.password_hasher import PasswordHasher
from api.persistence.repository.user import UserRepository
from api.persistence.repository.user_token import UserTokenRepository


def _new_raw_token() -> str:
    """Create a random bearer token.

    Returns:
        A URL safe random string.
    """
    return secrets.token_urlsafe(32)


@dataclass
class AuthenticateUser:
    """Exchange a nickname and password for a new bearer token.

    Attributes:
        users: Stores the users.
        tokens: Stores the token hashes.
        password_hasher: Hashes and verifies passwords.
        pepper: Secret added to every password hash.
        clock: Returns the current moment.
        token_factory: Creates the raw token.
        token_lifetime: Validity of the token; None means it never expires.
    """

    users: UserRepository
    tokens: UserTokenRepository
    password_hasher: PasswordHasher
    pepper: bytes
    clock: Callable[[], datetime]
    token_factory: Callable[[], str] = _new_raw_token
    token_lifetime: timedelta | None = None  # None means no expiration

    def execute(self, nickname: str, password: str) -> str:
        """Authenticate a user and issue a token.

        Only the hash of the token is stored; the raw token is returned once.

        Args:
            nickname: Login name.
            password: Password in plain text.

        Returns:
            The raw bearer token.

        Raises:
            AuthenticationError: If the credentials are invalid.
            PasswordChangeRequired: If the user still has the initial
                password.
        """
        user = self.users.get_by_nickname(nickname)

        if user is None or not self.password_hasher.verify_password(
            password, user.salt, user.password, self.pepper
        ):
            raise AuthenticationError("Invalid credentials")

        if user.must_change_password:
            raise PasswordChangeRequired(
                "Change the password before requesting a token"
            )

        now = self.clock()
        raw_token = self.token_factory()

        self.tokens.create(
            UserToken(
                signature=token_rules.signature_of(raw_token),
                user_id=user.id,
                created_at=now,
                expires_at=(
                    now + self.token_lifetime if self.token_lifetime else None
                ),
            )
        )

        # Return the raw token once. Never persist it.
        return raw_token
