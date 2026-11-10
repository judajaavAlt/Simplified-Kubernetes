from datetime import timedelta

import pytest

from api.data.models import BlobKind, SessionStatus
from api.domain import checksum, chunking
from api.domain.errors import (
    ChecksumMismatch,
    Conflict,
    InvalidInput,
    NotFound,
    PermissionDenied,
)
from transfer_helpers import MAX_SIZE, TTL, push, use_cases


pytestmark = pytest.mark.unit

MB = chunking.CHUNK_SIZE
CONTENT = b"a" * MB + b"b" * MB + b"c" * 10  # 3 pieces
SIGNATURE = checksum.sha256_hex(CONTENT)
PIECES = chunking.split(CONTENT)


def start(w, actor=None, content=CONTENT, **kwargs):
    args = dict(
        repository="org/app",
        kind=BlobKind.LAYER,
        signature=checksum.sha256_hex(content),
        size=len(content),
        layers=None,
    )
    args.update(kwargs)
    return use_cases(w).start_upload.execute(actor or w.devops, **args)


def send(w, upload_id, index, piece=None, signature=None, actor=None):
    piece = PIECES[index] if piece is None else piece
    use_cases(w).upload_chunk.execute(
        actor or w.devops,
        upload_id,
        index,
        signature or checksum.sha256_hex(piece),
        piece,
    )


def send_all(w, upload_id):
    for index in range(len(PIECES)):
        send(w, upload_id, index)


# ------------------------------------------------------------------
# StartUpload (handshake)
# ------------------------------------------------------------------


def test_start_opens_a_session_and_announces_the_pieces(world):
    ticket = start(world)

    assert ticket.status == "started"
    assert ticket.pieces == 3
    session = world.uploads.get(ticket.upload_id)
    assert session.status is SessionStatus.OPEN
    assert session.blob_signature == SIGNATURE
    assert session.user_id == world.devops.id
    assert ("upload.start", "started") in world.audit.names()


def test_start_creates_the_repository_on_first_push(world):
    start(world, repository="org/new")

    assert world.repos.get_by_name("org/new") is not None


def test_developer_cannot_upload(world):
    with pytest.raises(PermissionDenied):
        start(world, actor=world.developer)


@pytest.mark.parametrize(
    "override",
    [
        {"repository": "no-org"},
        {"signature": "not-a-sha"},
        {"size": -1},
        {"size": MAX_SIZE + 1},
        {"layers": ["a" * 64]},  # a layer cannot depend on layers
    ],
)
def test_start_rejects_invalid_requests(world, override):
    with pytest.raises(InvalidInput):
        start(world, **override)


def test_manifest_layers_must_be_valid_signatures(world):
    with pytest.raises(InvalidInput):
        start(world, kind=BlobKind.MANIFEST, layers=["bad"])


def test_manifest_layers_must_already_be_in_the_repository(world):
    with pytest.raises(NotFound):
        start(world, kind=BlobKind.MANIFEST, layers=["a" * 64])


def test_existing_blob_is_not_uploaded_again(world):
    push(world, world.devops, CONTENT, repository="org/one")

    ticket = start(world, repository="org/two")

    assert ticket.status == "exists"
    assert ticket.upload_id is None
    repo = world.repos.get_by_name("org/two")
    assert world.layers.get(SIGNATURE, repo.id) is not None
    assert ("upload.start", "exists") in world.audit.names()


# ------------------------------------------------------------------
# UploadChunk (checksum + log per piece)
# ------------------------------------------------------------------


def test_chunk_is_stored_and_logged(world):
    ticket = start(world)

    send(world, ticket.upload_id, 0)

    session = world.uploads.get(ticket.upload_id)
    assert session.received == {0: checksum.sha256_hex(PIECES[0])}
    assert ("upload.chunk", "ok") in world.audit.names()


def test_chunk_with_wrong_checksum_is_rejected_but_session_survives(world):
    ticket = start(world)

    with pytest.raises(ChecksumMismatch):
        send(world, ticket.upload_id, 0, signature="f" * 64)

    session = world.uploads.get(ticket.upload_id)
    assert session.received == {}
    assert session.status is SessionStatus.OPEN
    assert ("upload.chunk", "rejected") in world.audit.names()


def test_every_chunk_but_the_last_must_be_one_megabyte(world):
    ticket = start(world)

    with pytest.raises(InvalidInput):
        send(world, ticket.upload_id, 0, piece=b"a" * 10)


@pytest.mark.parametrize("index", [-1, 3])
def test_chunk_index_must_be_in_range(world, index):
    ticket = start(world)

    with pytest.raises(InvalidInput):
        send(world, ticket.upload_id, index, piece=b"x")


def test_resending_a_chunk_is_idempotent(world):
    ticket = start(world)

    send(world, ticket.upload_id, 0)
    send(world, ticket.upload_id, 0)

    assert len(world.uploads.get(ticket.upload_id).received) == 1


def test_only_the_owner_sends_chunks(world):
    ticket = start(world)

    with pytest.raises(PermissionDenied):
        send(world, ticket.upload_id, 0, actor=world.admin)


def test_unknown_upload(world):
    with pytest.raises(NotFound):
        send(world, "missing", 0)


def test_expired_upload_rejects_chunks(world):
    ticket = start(world)
    world.clock.advance(TTL)

    with pytest.raises(Conflict):
        send(world, ticket.upload_id, 0)


def test_activity_keeps_the_session_alive(world):
    ticket = start(world)
    world.clock.advance(TTL - timedelta(minutes=1))
    send(world, ticket.upload_id, 0)
    world.clock.advance(TTL - timedelta(minutes=1))

    send(world, ticket.upload_id, 1)


# ------------------------------------------------------------------
# GetUploadStatus (resume)
# ------------------------------------------------------------------


def test_status_lists_received_and_missing_pieces(world):
    ticket = start(world)
    send(world, ticket.upload_id, 1)

    progress = use_cases(world).upload_status.execute(
        world.devops, ticket.upload_id
    )

    assert progress.status is SessionStatus.OPEN
    assert progress.received == [1]
    assert progress.missing == [0, 2]


# ------------------------------------------------------------------
# FinishUpload (verify the whole blob once)
# ------------------------------------------------------------------


def test_finish_requires_every_piece(world):
    ticket = start(world)
    send(world, ticket.upload_id, 0)

    with pytest.raises(InvalidInput):
        use_cases(world).finish_upload.execute(world.devops, ticket.upload_id)


def test_finish_commits_the_blob_with_ordered_metadata(world):
    ticket = start(world)
    send_all(world, ticket.upload_id)

    result = use_cases(world).finish_upload.execute(
        world.devops, ticket.upload_id
    )

    assert result == SIGNATURE
    metadata = world.storage.read_metadata(SIGNATURE)
    assert metadata.total_size == len(CONTENT)
    assert metadata.chunk_size == MB
    assert [p.signature for p in metadata.pieces] == [
        checksum.sha256_hex(p) for p in PIECES
    ]
    assert [p.size for p in metadata.pieces] == [MB, MB, 10]
    repo = world.repos.get_by_name("org/app")
    assert world.layers.get(SIGNATURE, repo.id) is not None
    assert world.uploads.get(ticket.upload_id).status is SessionStatus.COMPLETED
    assert ("upload.finish", "completed") in world.audit.names()


def test_finish_registers_a_manifest_with_its_layers(world):
    layer = push(world, world.devops, b"layer")
    manifest = push(
        world, world.devops, b"manifest",
        kind=BlobKind.MANIFEST, layers=[layer],
    )

    repo = world.repos.get_by_name("org/app")
    assert world.manifests.get(manifest, repo.id).layers == [layer]


def test_finish_detects_a_blob_that_does_not_match_its_signature(world):
    ticket = start(world, signature="f" * 64)
    send_all(world, ticket.upload_id)

    with pytest.raises(ChecksumMismatch):
        use_cases(world).finish_upload.execute(world.devops, ticket.upload_id)

    assert world.uploads.get(ticket.upload_id).status is SessionStatus.FAILED
    assert ticket.upload_id not in world.storage.temp
    assert not world.storage.exists("f" * 64)
    assert ("upload.finish", "failed") in world.audit.names()


def test_finish_twice_is_a_conflict(world):
    ticket = start(world)
    send_all(world, ticket.upload_id)
    use_cases(world).finish_upload.execute(world.devops, ticket.upload_id)

    with pytest.raises(Conflict):
        use_cases(world).finish_upload.execute(world.devops, ticket.upload_id)


def test_empty_blob_can_be_uploaded(world):
    assert push(world, world.devops, b"") == checksum.sha256_hex(b"")


# ------------------------------------------------------------------
# CancelUpload
# ------------------------------------------------------------------


def test_cancel_discards_the_pieces(world):
    ticket = start(world)
    send(world, ticket.upload_id, 0)

    use_cases(world).cancel_upload.execute(world.devops, ticket.upload_id)

    assert world.uploads.get(ticket.upload_id).status is SessionStatus.CANCELLED
    assert ticket.upload_id not in world.storage.temp
    assert ("upload.cancel", "cancelled") in world.audit.names()


def test_only_the_owner_cancels(world):
    ticket = start(world)

    with pytest.raises(PermissionDenied):
        use_cases(world).cancel_upload.execute(world.admin, ticket.upload_id)


def test_completed_upload_cannot_be_cancelled(world):
    ticket = start(world)
    send_all(world, ticket.upload_id)
    use_cases(world).finish_upload.execute(world.devops, ticket.upload_id)

    with pytest.raises(Conflict):
        use_cases(world).cancel_upload.execute(world.devops, ticket.upload_id)


# ------------------------------------------------------------------
# CleanupExpiredSessions
# ------------------------------------------------------------------


def test_cleanup_expires_idle_sessions_and_discards_their_pieces(world):
    ticket = start(world)
    send(world, ticket.upload_id, 0)
    world.clock.advance(TTL)

    expired = use_cases(world).cleanup.execute()

    assert expired == 1
    assert world.uploads.get(ticket.upload_id).status is SessionStatus.EXPIRED
    assert ticket.upload_id not in world.storage.temp


def test_cleanup_keeps_active_sessions(world):
    ticket = start(world)

    assert use_cases(world).cleanup.execute() == 0
    assert world.uploads.get(ticket.upload_id).status is SessionStatus.OPEN


def test_cleanup_requested_by_a_user_needs_the_admin_role(world):
    with pytest.raises(PermissionDenied):
        use_cases(world).cleanup.execute(world.devops)

    assert use_cases(world).cleanup.execute(world.admin) == 0
