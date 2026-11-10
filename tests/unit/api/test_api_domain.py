import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from api.data.models import Role
from api.domain import checksum, chunking, naming, permissions, sessions
from api.domain.errors import InvalidInput, PermissionDenied
from api.domain.permissions import Action


pytestmark = pytest.mark.unit

MB = 1024 * 1024


# ------------------------------------------------------------------
# checksum
# ------------------------------------------------------------------


def test_sha256_hex_of_bytes():
    assert checksum.sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_sha256_of_parts_equals_sha256_of_joined_parts():
    parts = [b"ab", b"", b"cd"]

    assert checksum.sha256_of_parts(parts) == checksum.sha256_hex(b"abcd")


@pytest.mark.parametrize("value", ["a" * 64, "0123456789abcdef" * 4])
def test_valid_sha256_hex(value):
    assert checksum.is_sha256_hex(value)


@pytest.mark.parametrize(
    "value", ["", "a" * 63, "a" * 65, "g" * 64, "A" * 64, None]
)
def test_invalid_sha256_hex(value):
    assert not checksum.is_sha256_hex(value)


def test_matches_when_content_has_the_signature():
    assert checksum.matches(b"abc", checksum.sha256_hex(b"abc"))


def test_does_not_match_other_content():
    assert not checksum.matches(b"abd", checksum.sha256_hex(b"abc"))


# ------------------------------------------------------------------
# chunking (pieces of 1 MB)
# ------------------------------------------------------------------


def test_chunk_size_is_one_megabyte():
    assert chunking.CHUNK_SIZE == MB


@pytest.mark.parametrize(
    "total,expected",
    [(0, 0), (1, 1), (MB, 1), (MB + 1, 2), (3 * MB, 3)],
)
def test_piece_count(total, expected):
    assert chunking.piece_count(total) == expected


def test_every_piece_is_one_megabyte_except_the_last():
    total = 2 * MB + 5

    assert chunking.piece_size(total, 0) == MB
    assert chunking.piece_size(total, 1) == MB
    assert chunking.piece_size(total, 2) == 5


@pytest.mark.parametrize("index", [-1, 3])
def test_piece_size_rejects_out_of_range_index(index):
    with pytest.raises(InvalidInput):
        chunking.piece_size(2 * MB + 5, index)


def test_split_produces_ordered_pieces_of_one_megabyte():
    data = b"x" * MB + b"y" * 10

    pieces = chunking.split(data)

    assert pieces == [b"x" * MB, b"y" * 10]


# ------------------------------------------------------------------
# permissions by role
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,action,allowed",
    [
        (Role.ADMIN, Action.PULL, True),
        (Role.ADMIN, Action.PUSH, True),
        (Role.ADMIN, Action.DELETE, True),
        (Role.ADMIN, Action.ADMINISTER, True),
        (Role.DEVOPS, Action.PULL, True),
        (Role.DEVOPS, Action.PUSH, True),
        (Role.DEVOPS, Action.DELETE, True),
        (Role.DEVOPS, Action.ADMINISTER, False),
        (Role.DEVELOPER, Action.PULL, True),
        (Role.DEVELOPER, Action.PUSH, False),
        (Role.DEVELOPER, Action.DELETE, False),
        (Role.DEVELOPER, Action.ADMINISTER, False),
    ],
)
def test_role_permissions(role, action, allowed):
    assert permissions.can(role, action) is allowed


def test_require_raises_when_role_is_not_allowed():
    with pytest.raises(PermissionDenied):
        permissions.require(Role.DEVELOPER, Action.PUSH)


def test_require_passes_when_role_is_allowed():
    permissions.require(Role.DEVOPS, Action.PUSH)


# ------------------------------------------------------------------
# naming rules
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["org/repo", "my-org/my.repo_1", "org/team/repo"]
)
def test_valid_repository_names(name):
    naming.validate_repository(name)


@pytest.mark.parametrize(
    "name",
    ["", "repo", "Org/Repo", "org//repo", "../repo", "org/repo/", "org/-repo"],
)
def test_invalid_repository_names(name):
    with pytest.raises(InvalidInput):
        naming.validate_repository(name)


@pytest.mark.parametrize("tag", ["latest", "v1.0.2", "1_0-rc"])
def test_valid_tags(tag):
    naming.validate_tag(tag)


@pytest.mark.parametrize("tag", ["", ".hidden", "a b", "x" * 129, "a" * 64])
def test_invalid_tags(tag):
    # A 64-char hex tag would be ambiguous with a manifest signature.
    with pytest.raises(InvalidInput):
        naming.validate_tag(tag)


@pytest.mark.parametrize("nickname", ["ana", "dev_ops.1", "a" * 32])
def test_valid_nicknames(nickname):
    naming.validate_nickname(nickname)


@pytest.mark.parametrize("nickname", ["", "ab", "a b", "a" * 33])
def test_invalid_nicknames(nickname):
    with pytest.raises(InvalidInput):
        naming.validate_nickname(nickname)


def test_password_needs_at_least_eight_characters():
    naming.validate_password("12345678")

    with pytest.raises(InvalidInput):
        naming.validate_password("1234567")


# ------------------------------------------------------------------
# session expiration
# ------------------------------------------------------------------


def test_session_expires_after_ttl_without_activity():
    last = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ttl = timedelta(hours=24)

    assert not sessions.is_expired(last, last + ttl - timedelta(seconds=1), ttl)
    assert sessions.is_expired(last, last + ttl, ttl)
