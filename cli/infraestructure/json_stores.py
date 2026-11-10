import json
from pathlib import Path

from cli.data.models import Credentials
from cli.persistence.settings_store import CredentialStore, SettingsStore


def _read(path: Path) -> dict:
    """Read a JSON object file.

    Args:
        path: File to read.

    Returns:
        Its content, or an empty dictionary if it does not exist.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    """Write a JSON object file, creating its folder.

    Args:
        path: File to write.
        data: Content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")


class JsonSettingsStore(SettingsStore):
    """Settings in ``config.json``; unknown keys are kept.

    Attributes:
        path: Settings file.
    """

    KEY = "work_prefix"

    def __init__(self, path: Path):
        """Create the store.

        Args:
            path: Settings file.
        """
        self.path = Path(path)

    def get_prefix(self) -> str | None:
        """Read the default prefix.

        Returns:
            The prefix, or None.
        """
        return _read(self.path).get(self.KEY)

    def set_prefix(self, prefix: str | None) -> None:
        """Save or remove the default prefix.

        Args:
            prefix: Prefix, or None to remove it.
        """
        data = _read(self.path)
        if prefix is None:
            data.pop(self.KEY, None)
        else:
            data[self.KEY] = prefix
        _write(self.path, data)


class JsonCredentialStore(CredentialStore):
    """Registry sessions in ``credentials.json``, one per ``host:port``.

    Tokens are stored as given by the registry; they do not expire.

    Attributes:
        path: Credentials file.
    """

    def __init__(self, path: Path):
        """Create the store.

        Args:
            path: Credentials file.
        """
        self.path = Path(path)

    def get(self, registry: str) -> Credentials | None:
        """Find the session of a registry.

        Args:
            registry: ``host:port``.

        Returns:
            The credentials, or None.
        """
        item = _read(self.path).get(registry)
        if item is None:
            return None
        return Credentials(registry, item["token"], item["nickname"],
                           item.get("secure", True))

    def save(self, credentials: Credentials) -> None:
        """Save or replace the session of a registry.

        Args:
            credentials: Credentials to save.
        """
        data = _read(self.path)
        data[credentials.registry] = {
            "token": credentials.token,
            "nickname": credentials.nickname,
            "secure": credentials.secure,
        }
        _write(self.path, data)

    def delete(self, registry: str) -> None:
        """Forget the session of a registry.

        Args:
            registry: ``host:port``.
        """
        data = _read(self.path)
        data.pop(registry, None)
        _write(self.path, data)
