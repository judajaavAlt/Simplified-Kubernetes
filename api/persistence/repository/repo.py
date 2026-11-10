from abc import ABC, abstractmethod

from api.data.models import Repo


class RepoRepository(ABC):
    """Port that stores template repositories."""

    @abstractmethod
    def create(self, repo: Repo) -> int:
        """Persist a new repository.

        Args:
            repo: Repository to store; its ``id`` is ignored.

        Returns:
            The identifier assigned to the repository.
        """

    @abstractmethod
    def get_by_id(self, repo_id: int) -> Repo | None:
        """Find a repository by identifier.

        Args:
            repo_id: Repository identifier.

        Returns:
            The repository, or None if it does not exist.
        """
        pass

    @abstractmethod
    def get_by_name(self, name: str) -> Repo | None:
        """Find a repository by name.

        Args:
            name: Repository name, ``<organization>/<repo>``.

        Returns:
            The repository, or None if it does not exist.
        """
        pass
