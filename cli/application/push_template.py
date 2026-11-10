"""``template push`` (C-30)."""
from dataclasses import dataclass

from cli.application.lookup import TemplateLookup, load_manifest
from cli.application.sessions import RegistrySessions
from cli.application.transfer import Report, upload_blob
from cli.data.models import Reference
from cli.domain import ids
from cli.domain.errors import ValidationError
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec


@dataclass(frozen=True)
class PushResult:
    """Outcome of ``template push``.

    Attributes:
        reference: Reference pushed.
        manifest_id: SHA-256 of the manifest.
        uploaded: Blobs sent.
        skipped: Blobs the registry already had.
    """

    reference: Reference
    manifest_id: str
    uploaded: int
    skipped: int


@dataclass
class PushTemplate:
    """Upload a local template to its registry.

    Attributes:
        lookup: Finds local templates.
        manifests: Manifest store.
        layers: Layer store.
        codec: YAML codec.
        sessions: Registry clients.
    """

    lookup: TemplateLookup
    manifests: BlobStore
    layers: BlobStore
    codec: DocumentCodec
    sessions: RegistrySessions

    def execute(self, name: str, report: Report) -> PushResult:
        """Upload the missing layers, then the manifest, then the tag.

        Args:
            name: Reference of the template (complete or short); it names
                the registry, the repository and the tag.
            report: Receives progress messages.

        Returns:
            What was uploaded.

        Raises:
            ValidationError: If ``name`` is an ID instead of a reference.
            NotFoundError: If the template does not exist.
            NotLoggedInError: If there is no session for the registry.
            RegistryError: If an upload fails.
        """
        manifest_id, reference = self.lookup.find(name)
        if reference is None:
            raise ValidationError(
                "Push needs a reference (host:port/org/repo:tag), not an ID; "
                "add one with 'easyk8s template tag'"
            )
        client = self.sessions.client(reference.registry)
        manifest = load_manifest(self.manifests, self.codec, manifest_id)
        repository = reference.repository_path
        uploaded = skipped = 0
        total = len(manifest.layers)
        for number, layer_id in enumerate(manifest.layers, start=1):
            label = f"layer {number}/{total} {ids.short(layer_id)}"
            sent = upload_blob(
                client, repository, "layer", layer_id,
                self.layers.read(layer_id), (),
                lambda event, label=label: report(f"{label}: {event}"),
            )
            report(f"{label}: {'pushed' if sent else 'already exists'}")
            uploaded, skipped = uploaded + sent, skipped + (not sent)
        label = f"manifest {ids.short(manifest_id)}"
        sent = upload_blob(
            client, repository, "manifest", manifest_id,
            self.manifests.read(manifest_id), manifest.layers,
            lambda event: report(f"{label}: {event}"),
        )
        report(f"{label}: {'pushed' if sent else 'already exists'}")
        uploaded, skipped = uploaded + sent, skipped + (not sent)
        client.set_tag(repository, reference.tag, manifest_id)
        return PushResult(reference, manifest_id, uploaded, skipped)
