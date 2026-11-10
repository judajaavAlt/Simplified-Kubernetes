"""``template pull`` (C-31)."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from cli.application.lookup import TemplateLookup
from cli.application.sessions import RegistrySessions
from cli.application.transfer import Report, download_blob
from cli.data.models import Reference
from cli.domain import documents, ids
from cli.domain.errors import RegistryError, ValidationError
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec
from cli.persistence.template_index import TemplateIndex


@dataclass(frozen=True)
class PullResult:
    """Outcome of ``template pull``.

    Attributes:
        reference: Reference pulled.
        manifest_id: SHA-256 of the manifest.
        downloaded: Blobs downloaded.
    """

    reference: Reference
    manifest_id: str
    downloaded: int


@dataclass
class PullTemplate:
    """Download a template from its registry into the local store.

    Attributes:
        lookup: Completes short references.
        index: Local index.
        manifests: Manifest store.
        layers: Layer store.
        codec: YAML codec.
        sessions: Registry clients.
        clock: Returns the current moment.
    """

    lookup: TemplateLookup
    index: TemplateIndex
    manifests: BlobStore
    layers: BlobStore
    codec: DocumentCodec
    sessions: RegistrySessions
    clock: Callable[[], datetime]

    def execute(self, name: str, report: Report) -> PullResult:
        """Download the manifest and the missing layers, then register them.

        Every piece and every blob is verified with SHA-256. Nothing is
        registered until everything was downloaded. The template is not
        instantiated; that is ``template setup``.

        Args:
            name: Reference, complete or short.
            report: Receives progress messages.

        Returns:
            What was downloaded.

        Raises:
            ValidationError: If the reference is not valid.
            NotLoggedInError: If there is no session for the registry.
            RegistryError: If the tag does not exist or a download fails.
        """
        reference = self.lookup.parse(name)
        client = self.sessions.client(reference.registry)
        repository = reference.repository_path
        remote = client.resolve(repository, reference.tag)
        downloaded = 0
        total = len(remote.layers)
        for number, layer_id in enumerate(remote.layers, start=1):
            label = f"layer {number}/{total} {ids.short(layer_id)}"
            if self.layers.exists(layer_id):
                report(f"{label}: already exists")
                continue
            content = download_blob(client, repository, layer_id,
                                    lambda e, label=label: report(f"{label}: {e}"))
            self.layers.save(layer_id, content)
            downloaded += 1
        manifest_id = remote.signature
        label = f"manifest {ids.short(manifest_id)}"
        if self.manifests.exists(manifest_id):
            content = self.manifests.read(manifest_id)
        else:
            content = download_blob(client, repository, manifest_id,
                                    lambda e: report(f"{label}: {e}"))
            downloaded += 1
        try:
            manifest = documents.manifest_from_document(self.codec.load(content))
        except ValidationError as error:
            raise RegistryError(f"The registry sent an invalid manifest: {error}")
        if manifest.layers != tuple(remote.layers):
            raise RegistryError("The manifest does not match its layers")
        self.manifests.save(manifest_id, content)
        size = len(content) + sum(len(self.layers.read(l)) for l in manifest.layers)
        self.index.add_manifest(manifest_id, manifest.layers, size, self.clock())
        self.index.set_tag(reference, manifest_id)
        return PullResult(reference, manifest_id, downloaded)
