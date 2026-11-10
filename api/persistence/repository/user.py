from abc import ABC, abstractmethod

from api.data.models import Role, User


class UserRepository(ABC):
    """Port that stores users."""

    @abstractmethod
    def create(self, user: User) -> int:
        """Persist a new user.

        Args:
            user: User to store; its ``id`` is ignored.

        Returns:
            The identifier assigned to the user.
        """

    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None:
        """Find a user by identifier.

        Args:
            user_id: User identifier.

        Returns:
            The user, or None if it does not exist.
        """
        pass

    @abstractmethod
    def get_by_nickname(self, nickname: str) -> User | None:
        """Find a user by nickname.

        Args:
            nickname: Login name.

        Returns:
            The user, or None if it does not exist.
        """
        pass

    @abstractmethod
    def update(self, user: User) -> None:
        """Persist the password, salt, role and password flag of a user.

        Args:
            user: User with the new values.
        """
        pass

    @abstractmethod
    def list_by_role(self, role: Role) -> list[User]:
        """List the users that have a role.

        Args:
            role: Role to filter by.

        Returns:
            Every user with that role.
        """
        pass
