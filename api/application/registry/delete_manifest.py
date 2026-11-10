from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.application.audit import record
from api.application.registry.lookup import find_manifest, find_repo
from api.data.models import User
from api.domain import permissions
from api.domain.permissions import Action
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.layer import LayerRepository
from api.persistence.repository.manifest import ManifestRepository
from api.persistence.repository.repo import RepoRepository
from api.persistence.repository.tag import TagRepository


@dataclass
class DeleteManifest:
    """Delete a manifest with its tags, unshared layers and orphan blobs.

    Attributes:
        repos: Stores the repositories.
        manifests: Registers the manifests of each repository.
        layers: Registers the layers of each repository.
        tags: Stores the tags.
        storage: Stores the blobs and the staged pieces.
        audit: Receives the audit events.
        clock: Returns the current moment.
    """

    repos: RepoRepository
    manifests: ManifestRepository
    layers: LayerRepository
    tags: TagRepository
    storage: BlobStorage
    audit: AuditLogRepository
    clock: Callable[[], datetime]

    def execute(self, actor: User, repository: str, reference: str) -> str:
        """Delete a manifest and collect its garbage.

        A blob is shared by every repository, so it is only deleted when no
        repository registers it anymore.

        Args:
            actor: User making the request.
            repository: Repository name, ``<organization>/<repo>``.
            reference: Tag or manifest SHA-256.

        Returns:
            SHA-256 of the deleted manifest.

        Raises:
            PermissionDenied: If the role cannot delete.
            NotFound: If the repository, tag or manifest do not exist.
        """
        permissions.require(actor.role, Action.DELETE)
        repo = find_repo(self.repos, repository)
        manifest = find_manifest(self.manifests, self.tags, repo, reference)

        self.tags.delete_by_manifest(repo.id, manifest.signature)
        self.manifests.delete(manifest.signature, repo.id)

        collected = []

        for layer in dict.fromkeys(manifest.layers):
            if not self.manifests.references_layer(layer, repo.id):
                self.layers.delete(layer, repo.id)
                collected.append(layer)

        # A blob is shared by every repository: keep it while one uses it.
        for signature in [manifest.signature, *collected]:
            if not (
                self.layers.exists_anywhere(signature)
                or self.manifests.exists_anywhere(signature)
            ):
                self.storage.delete(signature)

        record(self.audit, self.clock, actor.id, None, "manifest.delete",
               "ok", f"{repository}@{manifest.signature}")

        return manifest.signature
