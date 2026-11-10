from api.data.models import Manifest, Repo
from api.domain import checksum, naming
from api.domain.errors import NotFound
from api.persistence.repository.manifest import ManifestRepository
from api.persistence.repository.repo import RepoRepository
from api.persistence.repository.tag import TagRepository


def find_repo(repos: RepoRepository, repository: str) -> Repo:
    """Find a repository by name.

    Args:
        repos: Repository store.
        repository: Repository name, ``<organization>/<repo>``.

    Returns:
        The repository.

    Raises:
        InvalidInput: If the name is invalid.
        NotFound: If the repository does not exist.
    """
    naming.validate_repository(repository)
    repo = repos.get_by_name(repository)

    if repo is None:
        raise NotFound(f"Repository '{repository}' not found")

    return repo


def find_manifest(
    manifests: ManifestRepository,
    tags: TagRepository,
    repo: Repo,
    reference: str,
) -> Manifest:
    """Find a manifest by reference.

    A reference is a tag or a manifest SHA-256; both are unique.

    Args:
        manifests: Manifest registry.
        tags: Tag store.
        repo: Repository of the manifest.
        reference: Tag or manifest SHA-256.

    Returns:
        The manifest.

    Raises:
        NotFound: If the tag or the manifest do not exist.
    """
    if checksum.is_sha256_hex(reference):
        signature = reference
    else:
        tag = tags.get(repo.id, reference)

        if tag is None:
            raise NotFound(f"Tag '{reference}' not found")

        signature = tag.manifest_signature

    manifest = manifests.get(signature, repo.id)

    if manifest is None:
        raise NotFound("Manifest not found")

    return manifest
