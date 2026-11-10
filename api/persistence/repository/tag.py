from abc import ABC, abstractmethod

from api.data.models import Tag


class TagRepository(ABC):
    """Port that stores tags."""

    @abstractmethod
    def set(self, tag: Tag) -> None:
        """Point a tag to a manifest, overwriting the tag if it exists.

        Args:
            tag: Tag to store.
        """

    @abstractmethod
    def get(self, repo_id: int, tag: str) -> Tag | None:
        """Find a tag of a repository.

        Args:
            repo_id: Repository identifier.
            tag: Tag name.

        Returns:
            The tag, or None if it does not exist.
        """
        pass

    @abstractmethod
    def list_by_repo(self, repo_id: int) -> list[Tag]:
        """List the tags of a repository.

        Args:
            repo_id: Repository identifier.

        Returns:
            Every tag of the repository.
        """
        pass

    @abstractmethod
    def delete_by_manifest(
        self, repo_id: int, manifest_signature: str
    ) -> None:
        """Delete every tag that points to a manifest.

        Args:
            repo_id: Repository identifier.
            manifest_signature: SHA-256 of the manifest.
        """
        pass
