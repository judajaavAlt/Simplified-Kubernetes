import pytest

import api.data.models as models
from api.data.models import Role, User


pytestmark = pytest.mark.unit


def test_roles_are_admin_devops_and_developer():
    assert {role.value for role in Role} == {"admin", "devops", "developer"}


def test_role_can_be_built_from_its_stored_value():
    assert Role("devops") is Role.DEVOPS


def test_user_has_a_role():
    user = User(
        id=1,
        nickname="ana",
        password="hash",
        salt="salt",
        role=Role.DEVELOPER,
    )

    assert user.role is Role.DEVELOPER


def test_new_user_must_change_password_by_default():
    user = User(
        id=1,
        nickname="ana",
        password="hash",
        salt="salt",
        role=Role.DEVELOPER,
    )

    assert user.must_change_password is True


def test_permit_model_no_longer_exists():
    # Roles live in the user: one API deployment = one organization.
    assert not hasattr(models, "Permit")


def _now():
    from datetime import datetime, timezone
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_blob_kinds_are_layer_and_manifest():
    assert {kind.value for kind in models.BlobKind} == {"layer", "manifest"}


def test_session_statuses():
    assert {status.value for status in models.SessionStatus} == {
        "open", "completed", "failed", "cancelled", "expired"
    }


def test_new_upload_session_is_open_and_empty():
    session = models.UploadSession(
        id="u1",
        user_id=1,
        repo_id=1,
        kind=models.BlobKind.LAYER,
        blob_signature="a" * 64,
        total_size=10,
        created_at=_now(),
        last_activity=_now(),
    )

    assert session.status is models.SessionStatus.OPEN
    assert session.received == {}
    assert session.layers == []


def test_new_download_session_is_open():
    session = models.DownloadSession(
        id="d1",
        user_id=1,
        repo_id=1,
        blob_signature="a" * 64,
        created_at=_now(),
        last_activity=_now(),
    )

    assert session.status is models.SessionStatus.OPEN


def test_manifest_keeps_the_ordered_layers_it_needs():
    manifest = models.Manifest(
        signature="m" * 64, repo_id=1, layers=["a" * 64, "b" * 64]
    )

    assert manifest.layers == ["a" * 64, "b" * 64]


def test_blob_metadata_lists_ordered_pieces():
    metadata = models.BlobMetadata(
        signature="a" * 64,
        total_size=3,
        chunk_size=1024 * 1024,
        pieces=[models.PieceInfo(index=0, signature="b" * 64, size=3)],
    )

    assert metadata.pieces[0].index == 0


def test_token_does_not_expire_by_default():
    token = models.UserToken(signature="t", user_id=1, created_at=_now())

    assert token.expires_at is None
    assert token.revoked_at is None


def test_temp_file_model_no_longer_exists():
    # Replaced by UploadSession + BlobStorage.
    assert not hasattr(models, "TempFile")
