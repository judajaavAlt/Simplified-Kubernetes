from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.domain import naming
from api.domain.errors import AuthenticationError, InvalidInput
from api.domain.password_hasher import PasswordHasher
from api.persistence.repository.user import UserRepository
from api.persistence.repository.user_token import UserTokenRepository


@dataclass
class ChangePassword:
    """Replace a user's password and revoke the user's tokens.

    Attributes:
        users: Stores the users.
        tokens: Stores the token hashes.
        password_hasher: Hashes and verifies passwords.
        pepper: Secret added to every password hash.
        clock: Returns the current moment.
    """

    users: UserRepository
    tokens: UserTokenRepository
    password_hasher: PasswordHasher
    pepper: bytes
    clock: Callable[[], datetime]

    def execute(
        self, nickname: str, current_password: str, new_password: str
    ) -> None:
        """Change the password of a user.

        Clears ``must_change_password`` and revokes every token, so old
        sessions must log in again.

        Args:
            nickname: Login name.
            current_password: Password in use.
            new_password: Password that replaces it.

        Raises:
            AuthenticationError: If the current credentials are invalid.
            InvalidInput: If the new password is too short or equals the
                current one.
        """
        user = self.users.get_by_nickname(nickname)

        if user is None or not self.password_hasher.verify_password(
            current_password, user.salt, user.password, self.pepper
        ):
            raise AuthenticationError("Invalid credentials")

        naming.validate_password(new_password)

        if new_password == current_password:
            raise InvalidInput("The new password must be different")

        user.password, user.salt = self.password_hasher.hash_password(
            new_password, self.pepper
        )
        user.must_change_password = False
        self.users.update(user)

        # Old sessions must log in again with the new password.
        self.tokens.revoke_all_for_user(user.id, self.clock())
