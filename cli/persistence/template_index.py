from abc import ABC, abstractmethod
from datetime import datetime

from cli.data.models import ManifestRecord, Reference


class TemplateIndex(ABC):
    """Port of the local index of templates (C-17).

    The manifests are the source of truth; the index organizes them by
    reference, tag and layer, and remembers which dry runs were done.
    """

    @abstractmethod
    def initialize(self) -> None:
        """Create the index structure if it does not exist."""

    @abstractmethod
    def add_manifest(
        self,
        manifest_id: str,
        layers: tuple[str, ...],
        size: int,
        created_at: datetime,
    ) -> None:
        """Register a manifest; does nothing if it is already registered.

        Args:
            manifest_id: SHA-256 of the manifest.
            layers: SHA-256 of its layers, in order.
            size: Size of the manifest plus its layers, in bytes.
            created_at: Moment it was created or pulled.
        """

    @abstractmethod
    def has_manifest(self, manifest_id: str) -> bool:
        """Check whether a manifest is registered.

        Args:
            manifest_id: SHA-256 of the manifest.

        Returns:
            True if it is registered.
        """

    @abstractmethod
    def manifest_ids(self) -> list[str]:
        """List the IDs of every registered manifest.

        Returns:
            The IDs.
        """

    @abstractmethod
    def layers_of(self, manifest_id: str) -> tuple[str, ...]:
        """List the layers of a manifest.

        Args:
            manifest_id: SHA-256 of the manifest.

        Returns:
            The layers in order; empty if the manifest is unknown.
        """

    @abstractmethod
    def remove_manifest(self, manifest_id: str) -> None:
        """Unregister a manifest together with its tags.

        Args:
            manifest_id: SHA-256 of the manifest.
        """

    @abstractmethod
    def list_manifests(self) -> list[ManifestRecord]:
        """List every manifest with its tags.

        Returns:
            The records, newest first.
        """

    @abstractmethod
    def set_tag(self, reference: Reference, manifest_id: str) -> None:
        """Point a reference to a manifest, overwriting it if it exists.

        Args:
            reference: Complete reference.
            manifest_id: SHA-256 of the manifest.
        """

    @abstractmethod
    def get_tag(self, reference: Reference) -> str | None:
        """Find the manifest a reference points to.

        Args:
            reference: Complete reference.

        Returns:
            The manifest ID, or None if the reference does not exist.
        """

    @abstractmethod
    def remove_tag(self, reference: Reference) -> None:
        """Delete a reference; the manifest is kept.

        Args:
            reference: Complete reference.
        """

    @abstractmethod
    def tags_of(self, manifest_id: str) -> list[Reference]:
        """List the references that point to a manifest.

        Args:
            manifest_id: SHA-256 of the manifest.

        Returns:
            The references.
        """

    @abstractmethod
    def layer_in_use(self, layer_id: str) -> bool:
        """Check whether any registered manifest needs a layer.

        Args:
            layer_id: SHA-256 of the layer.

        Returns:
            True if at least one manifest uses it.
        """

    @abstractmethod
    def clear_templates(self) -> None:
        """Unregister every manifest and tag; dry runs are kept."""

    @abstractmethod
    def record_dry_run(self, key: str, stage: str, at: datetime) -> None:
        """Remember that a stage of a template was run with ``--dry-run``.

        Args:
            key: Manifest ID (or the SHA-256 of an old config.template).
            stage: ``build`` or ``deploy``.
            at: Moment of the dry run.
        """

    @abstractmethod
    def has_dry_run(self, key: str, stage: str) -> bool:
        """Check whether a stage of a template already had a dry run.

        Args:
            key: Manifest ID (or the SHA-256 of an old config.template).
            stage: ``build`` or ``deploy``.

        Returns:
            True if the dry run was done on this machine.
        """
