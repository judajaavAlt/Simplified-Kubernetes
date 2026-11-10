from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.application.audit import record
from api.application.registry.lookup import find_manifest, find_repo
from api.data.models import Tag, User
from api.domain import checksum, naming, permissions
from api.domain.errors import InvalidInput
from api.domain.permissions import Action
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.manifest import ManifestRepository
from api.persistence.repository.repo import RepoRepository
from api.persistence.repository.tag import TagRepository


@dataclass
class TagManifest:
    """Point a tag to a manifest; a repeated tag is overwritten, like Docker.

    Attributes:
        repos: Stores the repositories.
        manifests: Registers the manifests of each repository.
        tags: Stores the tags.
        audit: Receives the audit events.
        clock: Returns the current moment.
    """

    repos: RepoRepository
    manifests: ManifestRepository
    tags: TagRepository
    audit: AuditLogRepository
    clock: Callable[[], datetime]

    def execute(
        self, actor: User, repository: str, tag: str, manifest_signature: str
    ) -> None:
        """Create or move a tag.

        Args:
            actor: User making the request.
            repository: Repository name, ``<organization>/<repo>``.
            tag: Tag name.
            manifest_signature: SHA-256 of the manifest.

        Raises:
            PermissionDenied: If the role cannot push.
            InvalidInput: If the tag or the signature are invalid.
            NotFound: If the repository or the manifest do not exist.
        """
        permissions.require(actor.role, Action.PUSH)
        naming.validate_tag(tag)

        if not checksum.is_sha256_hex(manifest_signature):
            raise InvalidInput("Expected a manifest SHA-256 hex digest")

        repo = find_repo(self.repos, repository)
        manifest = find_manifest(
            self.manifests, self.tags, repo, manifest_signature
        )

        self.tags.set(
            Tag(manifest_signature=manifest.signature, repo_id=repo.id, tag=tag)
        )

        record(self.audit, self.clock, actor.id, None,
               "tag.set", "ok", f"{repository}:{tag}")
