from dataclasses import dataclass

from api.data.models import Role, User
from api.domain import naming
from api.domain.errors import Conflict
from api.domain.password_hasher import PasswordHasher
from api.persistence.repository.user import UserRepository


@dataclass
class BootstrapAdmin:
    """Create the first admin locally, before the API is exposed.

    Attributes:
        users: Stores the users.
        password_hasher: Hashes and verifies passwords.
        pepper: Secret added to every password hash.
    """

    users: UserRepository
    password_hasher: PasswordHasher
    pepper: bytes

    def execute(self, nickname: str, password: str) -> int:
        """Create the admin account.

        The admin does not need to change the password afterwards.

        Args:
            nickname: Login name of the admin.
            password: Password in plain text.

        Returns:
            Identifier of the new admin.

        Raises:
            Conflict: If an admin or the nickname already exists.
            InvalidInput: If the nickname or password are invalid.
        """
        if self.users.list_by_role(Role.ADMIN):
            raise Conflict("An admin already exists")

        naming.validate_nickname(nickname)
        naming.validate_password(password)

        if self.users.get_by_nickname(nickname) is not None:
            raise Conflict("Nickname already exists")

        password_hash, salt = self.password_hasher.hash_password(
            password, self.pepper
        )

        return self.users.create(
            User(
                id=0,  # The repository assigns the real ID.
                nickname=nickname,
                password=password_hash,
                salt=salt,
                role=Role.ADMIN,
                must_change_password=False,
            )
        )
