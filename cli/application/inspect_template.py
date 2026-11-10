"""``template inspect`` (C-15)."""
from dataclasses import dataclass

from cli.application.lookup import TemplateLookup, load_manifest
from cli.data.models import Manifest
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec


@dataclass
class InspectTemplate:
    """Show the documentation, variables and commands of a template.

    Attributes:
        lookup: Finds local templates.
        manifests: Manifest store.
        codec: YAML codec.
    """

    lookup: TemplateLookup
    manifests: BlobStore
    codec: DocumentCodec

    def execute(self, name: str) -> tuple[str, Manifest]:
        """Read the manifest of a local template.

        Args:
            name: Reference, ID or ID prefix.

        Returns:
            The manifest ID and the manifest.

        Raises:
            NotFoundError: If the template does not exist.
            AmbiguousReferenceError: If an ID prefix is ambiguous.
        """
        manifest_id, _ = self.lookup.find(name)
        return manifest_id, load_manifest(self.manifests, self.codec, manifest_id)
