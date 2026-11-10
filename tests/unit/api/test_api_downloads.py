import pytest

from api.data.models import SessionStatus
from api.domain import checksum, chunking
from api.domain.errors import (
    Conflict,
    InvalidInput,
    NotFound,
    PermissionDenied,
)
from transfer_helpers import TTL, push, use_cases


pytestmark = pytest.mark.unit

CONTENT = b"z" * chunking.CHUNK_SIZE + b"end"
SIGNATURE = checksum.sha256_hex(CONTENT)


@pytest.fixture
def pushed(world):
    push(world, world.devops, CONTENT)
    return world


def start(w, actor=None, repository="org/app", signature=SIGNATURE):
    return use_cases(w).start_download.execute(
        actor or w.developer, repository, signature
    )


# ------------------------------------------------------------------
# StartDownload (handshake)
# ------------------------------------------------------------------


@pytest.mark.parametrize("actor", ["admin", "devops", "developer"])
def test_every_role_can_pull(pushed, actor):
    ticket = start(pushed, actor=getattr(pushed, actor))

    assert ticket.metadata.signature == SIGNATURE
    assert len(ticket.metadata.pieces) == 2


def test_start_opens_an_active_download_and_logs_it(pushed):
    ticket = start(pushed)

    session = pushed.downloads.get(ticket.download_id)
    assert session.status is SessionStatus.OPEN
    assert session.user_id == pushed.developer.id
    assert ("download.start", "started") in pushed.audit.names()


def test_unknown_repository(pushed):
    with pytest.raises(NotFound):
        start(pushed, repository="org/other")


def test_blob_must_belong_to_the_repository(pushed):
    push(pushed, pushed.devops, b"other", repository="org/other")

    with pytest.raises(NotFound):
        start(pushed, signature=checksum.sha256_hex(b"other"))


def test_invalid_signature(pushed):
    with pytest.raises(InvalidInput):
        start(pushed, signature="bad")


# ------------------------------------------------------------------
# DownloadChunk
# ------------------------------------------------------------------


def test_pieces_come_with_their_signature(pushed):
    ticket = start(pushed)
    uc = use_cases(pushed)

    pieces = [
        uc.download_chunk.execute(pushed.developer, ticket.download_id, i)
        for i in range(2)
    ]

    assert b"".join(p.content for p in pieces) == CONTENT
    for piece in pieces:
        assert checksum.matches(piece.content, piece.signature)
    assert ("download.chunk", "ok") in pushed.audit.names()


def test_chunk_index_out_of_range(pushed):
    ticket = start(pushed)

    with pytest.raises(InvalidInput):
        use_cases(pushed).download_chunk.execute(
            pushed.developer, ticket.download_id, 2
        )


def test_only_the_owner_downloads_chunks(pushed):
    ticket = start(pushed)

    with pytest.raises(PermissionDenied):
        use_cases(pushed).download_chunk.execute(
            pushed.devops, ticket.download_id, 0
        )


def test_expired_download(pushed):
    ticket = start(pushed)
    pushed.clock.advance(TTL)

    with pytest.raises(Conflict):
        use_cases(pushed).download_chunk.execute(
            pushed.developer, ticket.download_id, 0
        )


def test_unknown_download(pushed):
    with pytest.raises(NotFound):
        use_cases(pushed).download_chunk.execute(pushed.developer, "nope", 0)


# ------------------------------------------------------------------
# FinishDownload
# ------------------------------------------------------------------


def test_finish_with_matching_signature_completes(pushed):
    ticket = start(pushed)

    ok = use_cases(pushed).finish_download.execute(
        pushed.developer, ticket.download_id, SIGNATURE
    )

    assert ok is True
    session = pushed.downloads.get(ticket.download_id)
    assert session.status is SessionStatus.COMPLETED
    assert ("download.finish", "completed") in pushed.audit.names()


def test_finish_with_other_signature_is_logged_as_failed(pushed):
    ticket = start(pushed)

    ok = use_cases(pushed).finish_download.execute(
        pushed.developer, ticket.download_id, "f" * 64
    )

    assert ok is False
    assert pushed.downloads.get(ticket.download_id).status is SessionStatus.FAILED
    assert ("download.finish", "failed") in pushed.audit.names()


def test_finish_twice_is_a_conflict(pushed):
    ticket = start(pushed)
    uc = use_cases(pushed)
    uc.finish_download.execute(pushed.developer, ticket.download_id, SIGNATURE)

    with pytest.raises(Conflict):
        uc.finish_download.execute(
            pushed.developer, ticket.download_id, SIGNATURE
        )


# ------------------------------------------------------------------
# Active downloads (is someone downloading?)
# ------------------------------------------------------------------


def test_admin_sees_active_downloads(pushed):
    active = start(pushed)
    done = start(pushed)
    use_cases(pushed).finish_download.execute(
        pushed.developer, done.download_id, SIGNATURE
    )

    sessions = use_cases(pushed).active_downloads.execute(pushed.admin)

    assert [s.id for s in sessions] == [active.download_id]


def test_expired_downloads_are_not_active(pushed):
    start(pushed)
    pushed.clock.advance(TTL)

    assert use_cases(pushed).active_downloads.execute(pushed.admin) == []


def test_only_admin_lists_active_downloads(pushed):
    with pytest.raises(PermissionDenied):
        use_cases(pushed).active_downloads.execute(pushed.devops)
