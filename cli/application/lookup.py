"""Finding local templates by reference or ID (C-20, C-42)."""
from dataclasses import dataclass

from cli.data.models import Manifest, Prefix, Reference
from cli.domain import documents, ids, references
from cli.domain.errors import (
    AmbiguousReferenceError,
    NotFoundError,
    ValidationError,
)
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec
from cli.persistence.settings_store import SettingsStore
from cli.persistence.template_index import TemplateIndex


def current_prefix(settings: SettingsStore) -> Prefix | None:
    """Read the default prefix set with ``work set``.

    Args:
        settings: Settings store.

    Returns:
        The prefix, or None if none was set.
    """
    text = settings.get_prefix()
    return references.parse_prefix(text) if text else None


def load_manifest(
    manifests: BlobStore, codec: DocumentCodec, manifest_id: str
) -> Manifest:
    """Read a stored manifest.

    Args:
        manifests: Manifest store.
        codec: YAML codec.
        manifest_id: SHA-256 of the manifest.

    Returns:
        The manifest.

    Raises:
        NotFoundError: If it is not stored.
        ValidationError: If it is not a valid manifest.
    """
    return documents.manifest_from_document(
        codec.load(manifests.read(manifest_id))
    )


@dataclass
class TemplateLookup:
    """Resolves what the user wrote into a local template.

    Attributes:
        index: Local index.
        settings: Settings with the default prefix.
    """

    index: TemplateIndex
    settings: SettingsStore

    def parse(self, text: str) -> Reference:
        """Complete a reference with the default prefix.

        Args:
            text: Complete or short reference.

        Returns:
            The complete reference.

        Raises:
            ValidationError: If the reference is not valid.
        """
        return references.parse(text, current_prefix(self.settings))

    def find(self, name: str) -> tuple[str, Reference | None]:
        """Find a local template by reference, ID or unique ID prefix.

        Args:
            name: Reference (complete or short), complete ID or the first
                4 or more characters of an ID.

        Returns:
            The manifest ID and the reference, or None as reference when
            the template was found by ID.

        Raises:
            NotFoundError: If no template matches.
            AmbiguousReferenceError: If an ID prefix matches several
                templates.
        """
        try:
            reference = self.parse(name)
        except ValidationError:
            reference = None
        if reference is not None:
            manifest_id = self.index.get_tag(reference)
            if manifest_id:
                return manifest_id, reference
        if ids.is_id_prefix(name):
            matches = [i for i in self.index.manifest_ids() if i.startswith(name)]
            if len(matches) > 1:
                raise AmbiguousReferenceError(
                    f"'{name}' matches {len(matches)} templates; "
                    "write more characters of the ID"
                )
            if matches:
                return matches[0], None
        raise NotFoundError(f"Template '{name}' not found")
