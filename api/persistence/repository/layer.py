from abc import ABC, abstractmethod

from api.data.models import Layer


class LayerRepository(ABC):
    """Port that registers which repositories use each layer."""

    @abstractmethod
    def add(self, layer: Layer) -> None:
        """Register a layer in a repository.

        Does nothing if the layer is already registered there.

        Args:
            layer: Layer to register.
        """

    @abstractmethod
    def get(self, signature: str, repo_id: int) -> Layer | None:
        """Find a layer registered in a repository.

        Args:
            signature: SHA-256 of the layer.
            repo_id: Repository identifier.

        Returns:
            The layer, or None if the repository does not register it.
        """
        pass

    @abstractmethod
    def delete(self, signature: str, repo_id: int) -> None:
        """Remove a layer from a repository.

        Args:
            signature: SHA-256 of the layer.
            repo_id: Repository identifier.
        """
        pass

    @abstractmethod
    def exists_anywhere(self, signature: str) -> bool:
        """Check whether any repository still registers a layer.

        Args:
            signature: SHA-256 of the layer.

        Returns:
            True if at least one repository registers it.
        """
