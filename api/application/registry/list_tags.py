from dataclasses import dataclass

from api.application.registry.lookup import find_repo
from api.data.models import Tag, User
from api.domain import permissions
from api.domain.permissions import Action
from api.persistence.repository.repo import RepoRepository
from api.persistence.repository.tag import TagRepository


@dataclass
class ListTags:
    """List the tags of a repository.

    Attributes:
        repos: Stores the repositories.
        tags: Stores the tags.
    """

    repos: RepoRepository
    tags: TagRepository

    def execute(self, actor: User, repository: str) -> list[Tag]:
        """List the tags of a repository.

        Args:
            actor: User making the request.
            repository: Repository name, ``<organization>/<repo>``.

        Returns:
            Every tag of the repository.

        Raises:
            PermissionDenied: If the role cannot pull.
            NotFound: If the repository does not exist.
        """
        permissions.require(actor.role, Action.PULL)
        repo = find_repo(self.repos, repository)

        return self.tags.list_by_repo(repo.id)
