from abc import ABC, abstractmethod

from api.data.models import Manifest


class ManifestRepository(ABC):
    """Port that registers manifests and their layers."""

    @abstractmethod
    def add(self, manifest: Manifest) -> None:
        """Register a manifest and its ordered layers.

        Does nothing if the manifest is already registered.

        Args:
            manifest: Manifest to register.
        """

    @abstractmethod
    def get(self, signature: str, repo_id: int) -> Manifest | None:
        """Find a manifest of a repository.

        Args:
            signature: SHA-256 of the manifest.
            repo_id: Repository identifier.

        Returns:
            The manifest with its layers, or None if it does not exist.
        """
        pass

    @abstractmethod
    def delete(self, signature: str, repo_id: int) -> None:
        """Remove a manifest and its layer references from a repository.

        Args:
            signature: SHA-256 of the manifest.
            repo_id: Repository identifier.
        """
        pass

    @abstractmethod
    def references_layer(self, layer_signature: str, repo_id: int) -> bool:
        """Check whether any manifest of a repository needs a layer.

        Args:
            layer_signature: SHA-256 of the layer.
            repo_id: Repository identifier.

        Returns:
            True if at least one manifest references the layer.
        """

    @abstractmethod
    def exists_anywhere(self, signature: str) -> bool:
        """Check whether any repository still registers a manifest.

        Args:
            signature: SHA-256 of the manifest.

        Returns:
            True if at least one repository registers it.
        """
