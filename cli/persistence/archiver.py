from abc import ABC, abstractmethod

from cli.data.models import ArchiveEntry


class Archiver(ABC):
    """Port that packs the files of a layer into one blob (a tarball)."""

    @abstractmethod
    def pack(self, entries: list[ArchiveEntry]) -> bytes:
        """Pack entries reproducibly: same entries, same bytes (C-11).

        Args:
            entries: Files and folders of the layer.

        Returns:
            The packed layer.
        """

    @abstractmethod
    def unpack(self, content: bytes) -> list[ArchiveEntry]:
        """Read the entries of a packed layer.

        Args:
            content: Packed layer.

        Returns:
            The files and folders, in the stored order.

        Raises:
            ValidationError: If the content is not a valid layer.
        """
