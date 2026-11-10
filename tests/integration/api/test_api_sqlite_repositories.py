from datetime import datetime, timedelta, timezone

import pytest

from api.data.models import (
    AuditEvent,
    BlobKind,
    DownloadSession,
    Layer,
    Manifest,
    Repo,
    Role,
    SessionStatus,
    Tag,
    UploadSession,
    User,
    UserToken,
)
from api.infraestructure.sqlite.database import SQLiteDatabase
from api.infraestructure.sqlite.repositories import (
    SQLiteAuditLogRepository,
    SQLiteDownloadSessionRepository,
    SQLiteLayerRepository,
    SQLiteManifestRepository,
    SQLiteRepoRepository,
    SQLiteTagRepository,
    SQLiteUploadSessionRepository,
    SQLiteUserRepository,
    SQLiteUserTokenRepository,
)


pytestmark = pytest.mark.integration

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
A, B, C = "a" * 64, "b" * 64, "c" * 64


@pytest.fixture
def db(tmp_path):
    database = SQLiteDatabase(tmp_path / "data" / "registry.db")
    database.initialize()
    return database


def new_user(nickname="ana", role=Role.DEVOPS):
    return User(0, nickname, "hash", "salt", role, must_change_password=True)


def test_initialize_is_idempotent(db):
    db.initialize()


# ------------------------------------------------------------------
# Users and tokens
# ------------------------------------------------------------------


def test_user_roundtrip(db):
    users = SQLiteUserRepository(db)

    user_id = users.create(new_user())

    user = users.get_by_id(user_id)
    assert user == User(user_id, "ana", "hash", "salt", Role.DEVOPS, True)
    assert users.get_by_nickname("ana") == user
    assert users.get_by_nickname("nobody") is None
    assert users.get_by_id(999) is None


def test_user_update_and_list_by_role(db):
    users = SQLiteUserRepository(db)
    user_id = users.create(new_user())
    users.create(new_user("root", Role.ADMIN))

    user = users.get_by_id(user_id)
    user.password, user.must_change_password = "new", False
    users.update(user)

    assert users.get_by_id(user_id).password == "new"
    assert users.get_by_id(user_id).must_change_password is False
    assert [u.nickname for u in users.list_by_role(Role.ADMIN)] == ["root"]


def test_nickname_is_unique(db):
    users = SQLiteUserRepository(db)
    users.create(new_user())

    with pytest.raises(Exception):
        users.create(new_user())


def test_token_roundtrip_and_revocation(db):
    users = SQLiteUserRepository(db)
    tokens = SQLiteUserTokenRepository(db)
    user_id = users.create(new_user())

    tokens.create(UserToken("t1", user_id, NOW))
    tokens.create(UserToken("t2", user_id, NOW, NOW + timedelta(days=1)))

    assert tokens.get_by_signature("t1") == UserToken("t1", user_id, NOW)
    assert tokens.get_by_signature("t2").expires_at == NOW + timedelta(days=1)
    assert tokens.get_by_signature("nope") is None

    tokens.revoke("t1", NOW)
    assert tokens.get_by_signature("t1").revoked_at == NOW

    tokens.revoke_all_for_user(user_id, NOW + timedelta(hours=1))
    assert tokens.get_by_signature("t1").revoked_at == NOW  # unchanged
    assert tokens.get_by_signature("t2").revoked_at == NOW + timedelta(hours=1)


# ------------------------------------------------------------------
# Registry: repos, layers, manifests, tags
# ------------------------------------------------------------------


def test_repo_roundtrip(db):
    repos = SQLiteRepoRepository(db)

    repo_id = repos.create(Repo(0, "org/app"))

    assert repos.get_by_id(repo_id) == Repo(repo_id, "org/app")
    assert repos.get_by_name("org/app") == Repo(repo_id, "org/app")
    assert repos.get_by_name("org/none") is None


def test_layers(db):
    repos = SQLiteRepoRepository(db)
    layers = SQLiteLayerRepository(db)
    one = repos.create(Repo(0, "org/one"))
    two = repos.create(Repo(0, "org/two"))

    layers.add(Layer(A, one))
    layers.add(Layer(A, one))  # no-op
    layers.add(Layer(A, two))

    assert layers.get(A, one) == Layer(A, one)
    assert layers.get(B, one) is None

    layers.delete(A, one)
    assert layers.get(A, one) is None
    assert layers.exists_anywhere(A)

    layers.delete(A, two)
    assert not layers.exists_anywhere(A)


def test_manifests_keep_ordered_layers(db):
    repos = SQLiteRepoRepository(db)
    manifests = SQLiteManifestRepository(db)
    one = repos.create(Repo(0, "org/one"))

    manifests.add(Manifest(C, one, [B, A]))
    manifests.add(Manifest(C, one, [B, A]))  # no-op

    assert manifests.get(C, one) == Manifest(C, one, [B, A])
    assert manifests.references_layer(A, one)
    assert not manifests.references_layer(C, one)
    assert manifests.exists_anywhere(C)

    manifests.delete(C, one)
    assert manifests.get(C, one) is None
    assert not manifests.references_layer(A, one)
    assert not manifests.exists_anywhere(C)


def test_tags_are_overwritten_and_deleted_by_manifest(db):
    repos = SQLiteRepoRepository(db)
    tags = SQLiteTagRepository(db)
    one = repos.create(Repo(0, "org/one"))

    tags.set(Tag(A, one, "latest"))
    tags.set(Tag(B, one, "latest"))
    tags.set(Tag(B, one, "v1"))

    assert tags.get(one, "latest") == Tag(B, one, "latest")
    assert tags.get(one, "nope") is None
    assert sorted(t.tag for t in tags.list_by_repo(one)) == ["latest", "v1"]

    tags.delete_by_manifest(one, B)
    assert tags.list_by_repo(one) == []


# ------------------------------------------------------------------
# Sessions and audit
# ------------------------------------------------------------------


def test_upload_session_roundtrip(db):
    sessions = SQLiteUploadSessionRepository(db)
    session = UploadSession(
        id="u1", user_id=1, repo_id=1, kind=BlobKind.MANIFEST,
        blob_signature=A, total_size=10, created_at=NOW, last_activity=NOW,
        layers=[B, C],
    )

    sessions.create(session)
    assert sessions.get("u1") == session
    assert sessions.get("nope") is None

    session.received = {0: B, 2: C}
    session.last_activity = NOW + timedelta(minutes=5)
    sessions.update(session)
    assert sessions.get("u1") == session
    assert [s.id for s in sessions.list_open()] == ["u1"]

    session.status = SessionStatus.COMPLETED
    sessions.update(session)
    assert sessions.list_open() == []


def test_download_session_roundtrip(db):
    sessions = SQLiteDownloadSessionRepository(db)
    session = DownloadSession("d1", 1, 1, A, NOW, NOW)

    sessions.create(session)
    assert sessions.get("d1") == session
    assert [s.id for s in sessions.list_open()] == ["d1"]

    session.status = SessionStatus.FAILED
    sessions.update(session)
    assert sessions.get("d1").status is SessionStatus.FAILED
    assert sessions.list_open() == []


def test_audit_log_lists_newest_first(db):
    audit = SQLiteAuditLogRepository(db)

    audit.add(AuditEvent(1, "u1", "upload.start", "started", NOW, A))
    audit.add(AuditEvent(1, None, "tag.set", "ok", NOW + timedelta(1)))

    events = audit.list_recent()
    assert [e.event for e in events] == ["tag.set", "upload.start"]
    assert events[1] == AuditEvent(1, "u1", "upload.start", "started", NOW, A)
    assert len(audit.list_recent(limit=1)) == 1
