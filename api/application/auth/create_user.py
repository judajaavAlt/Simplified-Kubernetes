from dataclasses import dataclass

from api.data.models import Role, User
from api.domain import naming, permissions
from api.domain.errors import Conflict
from api.domain.password_hasher import PasswordHasher
from api.domain.permissions import Action
from api.persistence.repository.user import UserRepository


@dataclass
class CreateUser:
    """Let an admin create a user with a temporary password.

    Attributes:
        users: Stores the users.
        password_hasher: Hashes and verifies passwords.
        pepper: Secret added to every password hash.
    """

    users: UserRepository
    password_hasher: PasswordHasher
    pepper: bytes

    def execute(
        self, actor: User, nickname: str, password: str, role: Role
    ) -> int:
        """Create a user that must change the password on first use.

        Args:
            actor: Admin making the request.
            nickname: Login name of the new user.
            password: Temporary password in plain text.
            role: Role of the new user.

        Returns:
            Identifier of the new user.

        Raises:
            PermissionDenied: If the actor is not an admin.
            InvalidInput: If the nickname or password are invalid.
            Conflict: If the nickname already exists.
        """
        permissions.require(actor.role, Action.ADMINISTER)
        naming.validate_nickname(nickname)
        naming.validate_password(password)

        if self.users.get_by_nickname(nickname) is not None:
            raise Conflict("Nickname already exists")

        password_hash, salt = self.password_hasher.hash_password(
            password, self.pepper
        )

        # The new owner must replace the temporary password.
        return self.users.create(
            User(
                id=0,  # The repository assigns the real ID.
                nickname=nickname,
                password=password_hash,
                salt=salt,
                role=role,
                must_change_password=True,
            )
        )
