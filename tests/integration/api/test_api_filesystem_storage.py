import json

import pytest

from api.data.models import BlobMetadata, PieceInfo
from api.domain import checksum, chunking
from api.infraestructure.filesystem_blob_storage import FileSystemBlobStorage
from api.infraestructure.pbkdf2_password_hasher import Pbkdf2PasswordHasher


pytestmark = pytest.mark.integration

CONTENT = b"p" * chunking.CHUNK_SIZE + b"q" * 7
PIECES = chunking.split(CONTENT)
SIGNATURE = checksum.sha256_hex(CONTENT)
METADATA = BlobMetadata(
    signature=SIGNATURE,
    total_size=len(CONTENT),
    chunk_size=chunking.CHUNK_SIZE,
    pieces=[
        PieceInfo(i, checksum.sha256_hex(p), len(p))
        for i, p in enumerate(PIECES)
    ],
)


@pytest.fixture
def storage(tmp_path):
    return FileSystemBlobStorage(tmp_path / "storage")


def stage(storage, session="s1"):
    for piece in PIECES:
        storage.save_temp_piece(session, checksum.sha256_hex(piece), piece)


def test_temp_pieces_roundtrip(storage):
    stage(storage)

    sig = checksum.sha256_hex(PIECES[1])
    assert storage.read_temp_piece("s1", sig) == PIECES[1]


def test_commit_creates_blob_folder_with_pieces_and_metadata(storage, tmp_path):
    stage(storage)

    storage.commit("s1", METADATA)

    folder = tmp_path / "storage" / "blobs" / SIGNATURE
    names = sorted(p.name for p in folder.iterdir())
    assert names == sorted(
        [p.signature for p in METADATA.pieces] + ["metadata.json"]
    )
    stored = json.loads((folder / "metadata.json").read_text("utf-8"))
    assert stored["pieces"][1] == {
        "index": 1, "signature": METADATA.pieces[1].signature, "size": 7
    }
    # Staging area is cleaned.
    assert not (tmp_path / "storage" / "uploads" / "s1").exists()


def test_committed_blob_can_be_read_back(storage):
    stage(storage)
    storage.commit("s1", METADATA)

    assert storage.exists(SIGNATURE)
    assert storage.read_metadata(SIGNATURE) == METADATA
    content = b"".join(
        storage.read_piece(SIGNATURE, p.signature) for p in METADATA.pieces
    )
    assert content == CONTENT


def test_unknown_blob(storage):
    assert not storage.exists(SIGNATURE)
    assert storage.read_metadata(SIGNATURE) is None


def test_discard_and_delete(storage):
    stage(storage, "s1")
    stage(storage, "s2")
    storage.commit("s1", METADATA)

    storage.discard("s2")
    storage.discard("never-existed")
    storage.delete(SIGNATURE)
    storage.delete(SIGNATURE)

    assert not storage.exists(SIGNATURE)
    with pytest.raises(FileNotFoundError):
        storage.read_temp_piece("s2", METADATA.pieces[0].signature)


def test_empty_blob_has_only_metadata(storage):
    empty = BlobMetadata(checksum.sha256_hex(b""), 0, chunking.CHUNK_SIZE, [])

    storage.commit("no-pieces", empty)

    assert storage.read_metadata(empty.signature) == empty


@pytest.mark.parametrize("bad", ["../x", "a/b", "..", ""])
def test_ids_cannot_escape_the_storage_folder(storage, bad):
    with pytest.raises(ValueError):
        storage.save_temp_piece(bad, "a" * 64, b"x")

    with pytest.raises(ValueError):
        storage.read_piece("a" * 64, bad)


# ------------------------------------------------------------------
# PBKDF2 password hasher
# ------------------------------------------------------------------


def test_hasher_verifies_only_the_right_password_and_pepper():
    hasher = Pbkdf2PasswordHasher(iterations=1_000)

    password_hash, salt = hasher.hash_password("secret123", b"pepper")

    assert password_hash != "secret123"
    assert hasher.verify_password("secret123", salt, password_hash, b"pepper")
    assert not hasher.verify_password("secret124", salt, password_hash, b"pepper")
    assert not hasher.verify_password("secret123", salt, password_hash, b"other")


def test_hasher_uses_a_random_salt():
    hasher = Pbkdf2PasswordHasher(iterations=1_000)

    assert hasher.hash_password("x" * 8, b"p") != hasher.hash_password("x" * 8, b"p")
