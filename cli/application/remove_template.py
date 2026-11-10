"""``template rm`` (C-33, C-50)."""
from dataclasses import dataclass, field

from cli.application.lookup import TemplateLookup
from cli.application.sessions import RegistrySessions
from cli.domain.errors import ValidationError
from cli.persistence.blob_store import BlobStore
from cli.persistence.template_index import TemplateIndex


@dataclass(frozen=True)
class RemoveResult:
    """Outcome of ``template rm``.

    Attributes:
        untagged: References removed.
        deleted: Manifest and layers deleted, in that order.
    """

    untagged: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


@dataclass
class RemoveTemplate:
    """Remove a tag or a whole template, like ``docker rmi``.

    Attributes:
        index: Local index.
        manifests: Manifest store.
        layers: Layer store.
        lookup: Finds local templates.
        sessions: Registry clients, for ``--remote``.
    """

    index: TemplateIndex
    manifests: BlobStore
    layers: BlobStore
    lookup: TemplateLookup
    sessions: RegistrySessions

    def execute(self, name: str, remote: bool = False) -> RemoveResult:
        """Remove a reference or a template.

        With a reference, only that tag is removed; if it was the last one,
        the manifest and the layers no other manifest uses are deleted.
        With an ID, the manifest is deleted with every tag. With
        ``remote``, the manifest is first deleted in the registry too (the
        registry deletes it with all its tags).

        Args:
            name: Reference, ID or ID prefix.
            remote: Also delete the manifest in the registry.

        Returns:
            What was untagged and deleted.

        Raises:
            NotFoundError: If the template does not exist.
            NotLoggedInError: If ``remote`` and there is no session.
            ValidationError: If ``remote`` and the template has no
                reference to know its repository.
        """
        manifest_id, reference = self.lookup.find(name)
        tags = [reference] if reference else self.index.tags_of(manifest_id)
        if remote:
            self._remove_remote(manifest_id, reference, tags)
        for tag in tags:
            self.index.remove_tag(tag)
        untagged = [str(tag) for tag in tags]
        if self.index.tags_of(manifest_id):
            return RemoveResult(untagged, [])
        return RemoveResult(untagged, self._delete(manifest_id))

    def _remove_remote(self, manifest_id, reference, tags) -> None:
        """Delete the manifest in the registries.

        Args:
            manifest_id: SHA-256 of the manifest.
            reference: Reference given by the user, or None for an ID.
            tags: References of the manifest.

        Raises:
            ValidationError: If there is no reference to know the repository.
        """
        if reference is not None:
            client = self.sessions.client(reference.registry)
            client.delete_manifest(reference.repository_path, reference.tag)
            return
        if not tags:
            raise ValidationError(
                "The template has no reference, so its remote repository is "
                "unknown; delete it in the registry by reference"
            )
        targets = dict.fromkeys((t.registry, t.repository_path) for t in tags)
        for registry, repository in targets:
            self.sessions.client(registry).delete_manifest(repository, manifest_id)

    def _delete(self, manifest_id: str) -> list[str]:
        """Delete a manifest and the layers no other manifest uses.

        Args:
            manifest_id: SHA-256 of the manifest.

        Returns:
            The manifest and the deleted layers.
        """
        layers = self.index.layers_of(manifest_id)
        self.index.remove_manifest(manifest_id)
        self.manifests.delete(manifest_id)
        deleted = [manifest_id]
        for layer_id in dict.fromkeys(layers):
            if not self.index.layer_in_use(layer_id):
                self.layers.delete(layer_id)
                deleted.append(layer_id)
        return deleted
