import hashlib
import hmac
import secrets

from api.domain.password_hasher import PasswordHasher


class Pbkdf2PasswordHasher(PasswordHasher):
    """PBKDF2-HMAC-SHA256 with a random salt per user and a server pepper.

    Attributes:
        iterations: Number of PBKDF2 iterations.
    """

    def __init__(self, iterations: int = 600_000):
        """Create the hasher.

        Args:
            iterations: Number of PBKDF2 iterations.
        """
        self.iterations = iterations

    def hash_password(self, password: str, pepper: bytes) -> tuple[str, str]:
        """Hash a password with a new random salt and a pepper.

        Args:
            password: Password in plain text.
            pepper: Server secret appended to the password.

        Returns:
            A tuple ``(hash, salt)`` in hexadecimal.
        """
        salt = secrets.token_hex(16)
        return self._derive(password, salt, pepper), salt

    def verify_password(
        self,
        password: str,
        salt: str,
        expected_hash: str,
        pepper: bytes,
    ) -> bool:
        """Verify a password against its stored hash in constant time.

        Args:
            password: Password in plain text.
            salt: Salt stored with the hash.
            expected_hash: Stored hash.
            pepper: Secret used when the hash was created.

        Returns:
            True if the password is correct.
        """
        return hmac.compare_digest(
            self._derive(password, salt, pepper), expected_hash
        )

    def _derive(self, password: str, salt: str, pepper: bytes) -> str:
        """Derive the hash of a password.

        Args:
            password: Password in plain text.
            salt: Salt in hexadecimal.
            pepper: Server secret appended to the password.

        Returns:
            The hash in hexadecimal.
        """
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8") + pepper,
            bytes.fromhex(salt),
            self.iterations,
        ).hex()
