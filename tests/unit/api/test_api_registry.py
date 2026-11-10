import pytest

from api.data.models import BlobKind
from api.domain import checksum
from api.domain.errors import InvalidInput, NotFound, PermissionDenied
from transfer_helpers import push, use_cases


pytestmark = pytest.mark.unit


def push_template(w, layers_content, manifest_content, repository="org/app"):
    layers = [push(w, w.devops, c, repository=repository) for c in layers_content]
    manifest = push(
        w, w.devops, manifest_content, repository=repository,
        kind=BlobKind.MANIFEST, layers=layers,
    )
    return manifest, layers


def repo_id(w, name="org/app"):
    return w.repos.get_by_name(name).id


# ------------------------------------------------------------------
# TagManifest / ResolveReference / ListTags
# ------------------------------------------------------------------


def test_tag_points_to_a_manifest(world):
    manifest, _ = push_template(world, [b"l1"], b"m1")
    uc = use_cases(world)

    uc.tag_manifest.execute(world.devops, "org/app", "v1", manifest)

    assert uc.resolve.execute(world.developer, "org/app", "v1") == manifest
    assert ("tag.set", "ok") in world.audit.names()


def test_repeated_tag_is_overwritten_and_old_manifest_stays(world):
    first, _ = push_template(world, [b"l1"], b"m1")
    second, _ = push_template(world, [b"l2"], b"m2")
    uc = use_cases(world)

    uc.tag_manifest.execute(world.devops, "org/app", "latest", first)
    uc.tag_manifest.execute(world.devops, "org/app", "latest", second)

    assert uc.resolve.execute(world.developer, "org/app", "latest") == second
    # The old manifest is orphan but still exists.
    assert world.manifests.get(first, repo_id(world)) is not None


def test_developer_cannot_tag(world):
    manifest, _ = push_template(world, [b"l1"], b"m1")

    with pytest.raises(PermissionDenied):
        use_cases(world).tag_manifest.execute(
            world.developer, "org/app", "v1", manifest
        )


def test_tag_must_be_valid(world):
    manifest, _ = push_template(world, [b"l1"], b"m1")

    with pytest.raises(InvalidInput):
        use_cases(world).tag_manifest.execute(
            world.devops, "org/app", "bad tag", manifest
        )


def test_only_manifests_of_the_repository_can_be_tagged(world):
    layer = push(world, world.devops, b"just-a-layer")

    with pytest.raises(NotFound):
        use_cases(world).tag_manifest.execute(
            world.devops, "org/app", "v1", layer
        )


def test_resolve_accepts_a_signature(world):
    manifest, _ = push_template(world, [b"l1"], b"m1")

    assert use_cases(world).resolve.execute(
        world.developer, "org/app", manifest
    ) == manifest


@pytest.mark.parametrize("reference", ["missing", "f" * 64])
def test_resolve_unknown_reference(world, reference):
    push_template(world, [b"l1"], b"m1")

    with pytest.raises(NotFound):
        use_cases(world).resolve.execute(world.developer, "org/app", reference)


def test_list_tags(world):
    manifest, _ = push_template(world, [b"l1"], b"m1")
    uc = use_cases(world)
    uc.tag_manifest.execute(world.devops, "org/app", "v1", manifest)
    uc.tag_manifest.execute(world.devops, "org/app", "latest", manifest)

    tags = uc.list_tags.execute(world.developer, "org/app")

    assert sorted(t.tag for t in tags) == ["latest", "v1"]


# ------------------------------------------------------------------
# DeleteManifest + garbage collection
# ------------------------------------------------------------------


@pytest.mark.parametrize("by", ["tag", "signature"])
def test_delete_removes_manifest_tag_and_unshared_layers(world, by):
    shared = checksum.sha256_hex(b"shared")
    keep, _ = push_template(world, [b"shared"], b"keep")
    gone, layers = push_template(world, [b"shared", b"own"], b"gone")
    own = checksum.sha256_hex(b"own")
    uc = use_cases(world)
    uc.tag_manifest.execute(world.devops, "org/app", "v1", gone)

    reference = "v1" if by == "tag" else gone
    deleted = uc.delete_manifest.execute(world.devops, "org/app", reference)

    rid = repo_id(world)
    assert deleted == gone
    assert world.manifests.get(gone, rid) is None
    assert world.tags.get(rid, "v1") is None
    assert not world.storage.exists(gone)
    # Only the layer no other manifest needs is collected.
    assert world.layers.get(own, rid) is None
    assert not world.storage.exists(own)
    assert world.layers.get(shared, rid) is not None
    assert world.storage.exists(shared)
    assert world.manifests.get(keep, rid) is not None
    assert ("manifest.delete", "ok") in world.audit.names()


def test_blob_used_by_another_repository_is_kept(world):
    manifest, _ = push_template(world, [b"common"], b"m-app")
    push_template(world, [b"common"], b"m-other", repository="org/other")
    common = checksum.sha256_hex(b"common")

    use_cases(world).delete_manifest.execute(world.devops, "org/app", manifest)

    assert world.layers.get(common, repo_id(world)) is None
    assert world.storage.exists(common)


def test_developer_cannot_delete(world):
    manifest, _ = push_template(world, [b"l1"], b"m1")

    with pytest.raises(PermissionDenied):
        use_cases(world).delete_manifest.execute(
            world.developer, "org/app", manifest
        )


def test_delete_unknown_manifest(world):
    push_template(world, [b"l1"], b"m1")

    with pytest.raises(NotFound):
        use_cases(world).delete_manifest.execute(
            world.devops, "org/app", "missing"
        )
