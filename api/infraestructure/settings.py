import os
import secrets
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from api.domain.chunking import CHUNK_SIZE


def default_data_dir() -> Path:
    """Return the default data folder of the API.

    Returns:
        ``%LOCALAPPDATA%/judajaav/easyK8s-api`` on Windows, or
        ``~/.easyk8s-api`` elsewhere.
    """
    local = os.getenv("LOCALAPPDATA")

    if local:
        return Path(local) / "judajaav" / "easyK8s-api"

    return Path.home() / ".easyk8s-api"


def _load_or_create_pepper(data_dir: Path) -> bytes:
    """Read the pepper, generating it the first time.

    The pepper is a server secret: it is never stored in the database.

    Args:
        data_dir: Folder that holds ``pepper.key``.

    Returns:
        The pepper bytes.
    """
    path = data_dir / "pepper.key"

    if not path.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32), encoding="utf-8")

    return bytes.fromhex(path.read_text(encoding="utf-8").strip())


@dataclass(frozen=True)
class Settings:
    """Configuration of the API.

    Attributes:
        data_dir: Folder with the database, the blobs and ``pepper.key``.
        pepper: Secret added to every password hash.
        max_blob_size: Largest accepted blob, in bytes (1 GB by default).
        session_ttl: Inactivity after which a session expires.
        hash_iterations: Number of PBKDF2 iterations.
    """

    data_dir: Path
    pepper: bytes
    max_blob_size: int = 1024 * CHUNK_SIZE  # 1 GB
    session_ttl: timedelta = timedelta(hours=24)
    hash_iterations: int = 600_000

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        """Read the settings from environment variables.

        Variables:

        * ``EASYK8S_API_DATA``: data folder (database, blobs, ``pepper.key``).
        * ``EASYK8S_API_PEPPER``: pepper; generated in the data folder if absent.
        * ``EASYK8S_API_MAX_BLOB_SIZE``: largest blob, in bytes.
        * ``EASYK8S_API_SESSION_TTL_HOURS``: idle hours before a session expires.
        * ``EASYK8S_API_HASH_ITERATIONS``: PBKDF2 iterations.

        Args:
            env: Mapping to read instead of ``os.environ``.

        Returns:
            The settings.
        """
        env = os.environ if env is None else env
        data_dir = Path(env.get("EASYK8S_API_DATA") or default_data_dir())
        pepper = env.get("EASYK8S_API_PEPPER")

        return cls(
            data_dir=data_dir,
            pepper=(
                pepper.encode("utf-8")
                if pepper
                else _load_or_create_pepper(data_dir)
            ),
            max_blob_size=int(
                env.get("EASYK8S_API_MAX_BLOB_SIZE", cls.max_blob_size)
            ),
            session_ttl=timedelta(
                hours=float(env.get("EASYK8S_API_SESSION_TTL_HOURS", 24))
            ),
            hash_iterations=int(
                env.get("EASYK8S_API_HASH_ITERATIONS", cls.hash_iterations)
            ),
        )
