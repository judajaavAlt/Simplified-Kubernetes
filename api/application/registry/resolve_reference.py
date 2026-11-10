from dataclasses import dataclass

from api.application.registry.lookup import find_manifest, find_repo
from api.data.models import Manifest, User
from api.domain import permissions
from api.domain.permissions import Action
from api.persistence.repository.manifest import ManifestRepository
from api.persistence.repository.repo import RepoRepository
from api.persistence.repository.tag import TagRepository


@dataclass
class ResolveReference:
    """Turn a tag or signature into the manifest the CLI must pull.

    Attributes:
        repos: Stores the repositories.
        manifests: Registers the manifests of each repository.
        tags: Stores the tags.
    """

    repos: RepoRepository
    manifests: ManifestRepository
    tags: TagRepository

    def execute(self, actor: User, repository: str, reference: str) -> str:
        """Resolve a reference to a manifest signature.

        Args:
            actor: User making the request.
            repository: Repository name, ``<organization>/<repo>``.
            reference: Tag or manifest SHA-256.

        Returns:
            SHA-256 of the manifest.

        Raises:
            PermissionDenied: If the role cannot pull.
            NotFound: If the repository, tag or manifest do not exist.
        """
        return self.manifest(actor, repository, reference).signature

    def manifest(
        self, actor: User, repository: str, reference: str
    ) -> Manifest:
        """Resolve a reference to the manifest with its layers.

        Args:
            actor: User making the request.
            repository: Repository name, ``<organization>/<repo>``.
            reference: Tag or manifest SHA-256.

        Returns:
            The manifest.

        Raises:
            PermissionDenied: If the role cannot pull.
            NotFound: If the repository, tag or manifest do not exist.
        """
        permissions.require(actor.role, Action.PULL)
        repo = find_repo(self.repos, repository)

        return find_manifest(self.manifests, self.tags, repo, reference)
