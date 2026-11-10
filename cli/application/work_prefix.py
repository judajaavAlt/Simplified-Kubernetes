"""``work set`` and ``work show`` (C-27, C-42)."""
from dataclasses import dataclass

from cli.domain import references
from cli.persistence.settings_store import SettingsStore


@dataclass
class SetWorkPrefix:
    """Save the default prefix used to complete short references.

    Attributes:
        settings: Settings store.
    """

    settings: SettingsStore

    def execute(self, prefix: str | None) -> str | None:
        """Validate and save the prefix.

        Args:
            prefix: ``host:port``, ``host:port/org`` or
                ``host:port/org/repo``; None removes it.

        Returns:
            The saved prefix.

        Raises:
            ValidationError: If the prefix is not valid.
        """
        if prefix is not None:
            references.parse_prefix(prefix)
        self.settings.set_prefix(prefix)
        return prefix


@dataclass
class ShowWorkPrefix:
    """Read the default prefix.

    Attributes:
        settings: Settings store.
    """

    settings: SettingsStore

    def execute(self) -> str | None:
        """Read the prefix.

        Returns:
            The prefix, or None if none was set.
        """
        return self.settings.get_prefix()
