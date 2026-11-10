from api.data.models import BlobKind, Layer, Manifest
from api.persistence.repository.layer import LayerRepository
from api.persistence.repository.manifest import ManifestRepository


def register_blob(
    layers: LayerRepository,
    manifests: ManifestRepository,
    kind: BlobKind,
    signature: str,
    repo_id: int,
    manifest_layers: list[str],
) -> None:
    """Make a stored blob visible inside a repository.

    Args:
        layers: Layer registry.
        manifests: Manifest registry.
        kind: Whether the blob is a layer or a manifest.
        signature: SHA-256 of the blob.
        repo_id: Repository identifier.
        manifest_layers: For a manifest, the signatures of its layers.
    """
    if kind is BlobKind.LAYER:
        layers.add(Layer(signature=signature, repo_id=repo_id))
    else:
        manifests.add(
            Manifest(
                signature=signature,
                repo_id=repo_id,
                layers=list(manifest_layers),
            )
        )
