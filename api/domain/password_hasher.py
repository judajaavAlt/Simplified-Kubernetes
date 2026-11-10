from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    """Port that hashes and verifies passwords.

    The implementation lives in the infrastructure layer.
    """

    @abstractmethod
    def hash_password(self, password: str, pepper: bytes) -> tuple[str, str]:
        """Hash a password with a new random salt and a pepper.

        Args:
            password: Password in plain text.
            pepper: Secret shared by the whole API and not stored in the
                database.

        Returns:
            A tuple ``(hash, salt)``.
        """
        pass

    @abstractmethod
    def verify_password(
        self,
        password: str,
        salt: str,
        expected_hash: str,
        pepper: bytes,
    ) -> bool:
        """Verify a password against its stored hash.

        Args:
            password: Password in plain text.
            salt: Salt stored with the hash.
            expected_hash: Stored hash.
            pepper: Secret used when the hash was created.

        Returns:
            True if the password is correct.
        """
        pass
