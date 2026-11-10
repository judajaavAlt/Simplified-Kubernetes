"""``template reindex``: the index can be rebuilt from the manifests (C-17)."""
from dataclasses import dataclass

from cli.application.lookup import load_manifest
from cli.domain import references
from cli.domain.errors import ValidationError
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec
from cli.persistence.template_index import TemplateIndex


@dataclass
class RebuildIndex:
    """Rebuild the local index from the stored manifests.

    Each manifest gets back the reference it was created with; when several
    share a reference, the most recently stored one keeps it. Tags made with
    ``template tag`` are lost; dry runs are kept.

    Attributes:
        index: Local index.
        manifests: Manifest store.
        layers: Layer store.
        codec: YAML codec.
    """

    index: TemplateIndex
    manifests: BlobStore
    layers: BlobStore
    codec: DocumentCodec

    def execute(self) -> int:
        """Rebuild the index.

        Returns:
            Number of manifests registered.
        """
        self.index.clear_templates()
        count = 0
        for manifest_id, stored_at in sorted(self.manifests.list(),
                                             key=lambda item: item[1]):
            try:
                manifest = load_manifest(self.manifests, self.codec, manifest_id)
                reference = references.parse(manifest.reference)
            except ValidationError:
                continue
            size = len(self.manifests.read(manifest_id)) + sum(
                len(self.layers.read(layer))
                for layer in manifest.layers if self.layers.exists(layer)
            )
            self.index.add_manifest(manifest_id, manifest.layers, size, stored_at)
            self.index.set_tag(reference, manifest_id)
            count += 1
        return count
