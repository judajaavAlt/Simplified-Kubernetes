from fastapi import APIRouter, Depends, status

from api.data.models import User
from api.presentation.dependencies import current_user, get_services
from api.presentation.schemas import (
    DeletedResponse,
    ResolvedManifestResponse,
    TagItem,
    TagRequest,
    TagsResponse,
)
from api.presentation.services import ApiServices


router = APIRouter(tags=["registry"])


@router.put("/tags", status_code=status.HTTP_204_NO_CONTENT)
def tag_manifest(
    body: TagRequest,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Point a tag to a manifest, overwriting it if it exists.

    Args:
        body: Repository, tag and manifest signature.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.
    """
    services.tag_manifest.execute(
        user, body.repository, body.tag, body.manifest
    )


@router.get("/tags", response_model=TagsResponse)
def list_tags(
    repository: str,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """List the tags of a repository.

    Args:
        repository: Repository, ``<organization>/<repo>``.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The tags with their manifests.
    """
    tags = services.list_tags.execute(user, repository)
    return TagsResponse(
        tags=[TagItem(tag=t.tag, manifest=t.manifest_signature) for t in tags]
    )


@router.get("/manifests/resolve", response_model=ResolvedManifestResponse)
def resolve_manifest(
    repository: str,
    reference: str,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Resolve a tag or signature to a manifest and its layers.

    Args:
        repository: Repository, ``<organization>/<repo>``.
        reference: Tag or manifest SHA-256.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The manifest signature and its layers.
    """
    manifest = services.resolve.manifest(user, repository, reference)
    return ResolvedManifestResponse(
        signature=manifest.signature, layers=manifest.layers
    )


@router.delete("/manifests", response_model=DeletedResponse)
def delete_manifest(
    repository: str,
    reference: str,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Delete a manifest with its tags and unshared layers.

    Args:
        repository: Repository, ``<organization>/<repo>``.
        reference: Tag or manifest SHA-256.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The signature of the deleted manifest.
    """
    deleted = services.delete_manifest.execute(user, repository, reference)
    return DeletedResponse(deleted=deleted)
