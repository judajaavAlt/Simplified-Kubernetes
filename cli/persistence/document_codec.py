from abc import ABC, abstractmethod


class DocumentCodec(ABC):
    """Port that reads and writes YAML documents."""

    @abstractmethod
    def dump(self, document) -> bytes:
        """Write a document, keeping the key order.

        Args:
            document: Plain dictionaries, lists and scalars.

        Returns:
            The encoded document.
        """

    @abstractmethod
    def load(self, content: bytes):
        """Read a document.

        Args:
            content: Encoded document.

        Returns:
            Plain dictionaries, lists and scalars.

        Raises:
            ValidationError: If the content cannot be parsed.
        """

    @abstractmethod
    def problems(self, content: bytes) -> list[str]:
        """Find what makes a YAML file malformed, without raising.

        Every document of the file is checked (``---`` separates them).

        Args:
            content: YAML bytes.

        Returns:
            One message per problem, starting with ``line N:``: syntax
            errors, keys without a value (``name:`` with nothing after it)
            and empty list items. Explicit ``null`` or ``~`` is accepted.
        """
