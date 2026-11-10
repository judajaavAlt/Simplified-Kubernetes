"""
Composition root: the only place that knows the concrete implementations.
It builds every use case with its dependencies and injects them upwards.
"""
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI

from api.application.admin.list_audit_events import ListAuditEvents
from api.application.auth.authenticate_user import AuthenticateUser
from api.application.auth.bootstrap_admin import BootstrapAdmin
from api.application.auth.change_password import ChangePassword
from api.application.auth.create_user import CreateUser
from api.application.auth.revoke_token import RevokeToken
from api.application.auth.validate_token import ValidateToken
from api.application.download.download_chunk import DownloadChunk
from api.application.download.finish_download import FinishDownload
from api.application.download.list_active_downloads import (
    ListActiveDownloads,
)
from api.application.download.start_download import StartDownload
from api.application.registry.delete_manifest import DeleteManifest
from api.application.registry.list_tags import ListTags
from api.application.registry.resolve_reference import ResolveReference
from api.application.registry.tag_manifest import TagManifest
from api.application.upload.cancel_upload import CancelUpload
from api.application.upload.cleanup_expired_sessions import (
    CleanupExpiredSessions,
)
from api.application.upload.finish_upload import FinishUpload
from api.application.upload.get_upload_status import GetUploadStatus
from api.application.upload.start_upload import StartUpload
from api.application.upload.upload_chunk import UploadChunk
from api.infraestructure.filesystem_blob_storage import FileSystemBlobStorage
from api.infraestructure.pbkdf2_password_hasher import Pbkdf2PasswordHasher
from api.infraestructure.settings import Settings
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
from api.presentation.services import ApiServices
from api.userInterface.app import create_app


def utc_now() -> datetime:
    """Return the current moment in UTC.

    Returns:
        A timezone aware datetime.
    """
    return datetime.now(timezone.utc)


def _database(settings: Settings) -> SQLiteDatabase:
    """Open the registry database and create its tables if needed.

    Args:
        settings: API settings with the data folder.

    Returns:
        The initialized database.
    """
    database = SQLiteDatabase(settings.data_dir / "registry.db")
    database.initialize()
    return database


def build_services(
    settings: Settings, clock: Callable[[], datetime] = utc_now
) -> ApiServices:
    """Build every use case with its concrete dependencies.

    This is the composition root: the only place that knows the SQLite,
    filesystem and PBKDF2 implementations.

    Args:
        settings: API settings.
        clock: Returns the current moment; replaceable in tests.

    Returns:
        The use cases the presentation layer needs.
    """
    database = _database(settings)
    storage = FileSystemBlobStorage(settings.data_dir / "storage")
    hasher = Pbkdf2PasswordHasher(settings.hash_iterations)

    users = SQLiteUserRepository(database)
    tokens = SQLiteUserTokenRepository(database)
    repos = SQLiteRepoRepository(database)
    layers = SQLiteLayerRepository(database)
    manifests = SQLiteManifestRepository(database)
    tags = SQLiteTagRepository(database)
    uploads = SQLiteUploadSessionRepository(database)
    downloads = SQLiteDownloadSessionRepository(database)
    audit = SQLiteAuditLogRepository(database)
    ttl = settings.session_ttl

    return ApiServices(
        authenticate=AuthenticateUser(
            users=users, tokens=tokens, password_hasher=hasher,
            pepper=settings.pepper, clock=clock,
        ),
        change_password=ChangePassword(
            users=users, tokens=tokens, password_hasher=hasher,
            pepper=settings.pepper, clock=clock,
        ),
        validate_token=ValidateToken(tokens=tokens, users=users, clock=clock),
        revoke_token=RevokeToken(tokens=tokens, clock=clock),
        create_user=CreateUser(
            users=users, password_hasher=hasher, pepper=settings.pepper
        ),
        start_upload=StartUpload(
            repos=repos, layers=layers, manifests=manifests,
            sessions=uploads, storage=storage, audit=audit, clock=clock,
            max_size=settings.max_blob_size,
        ),
        upload_chunk=UploadChunk(
            sessions=uploads, storage=storage, audit=audit, clock=clock,
            session_ttl=ttl,
        ),
        upload_status=GetUploadStatus(sessions=uploads),
        finish_upload=FinishUpload(
            sessions=uploads, storage=storage, layers=layers,
            manifests=manifests, audit=audit, clock=clock, session_ttl=ttl,
        ),
        cancel_upload=CancelUpload(
            sessions=uploads, storage=storage, audit=audit, clock=clock
        ),
        start_download=StartDownload(
            repos=repos, layers=layers, manifests=manifests,
            storage=storage, sessions=downloads, audit=audit, clock=clock,
        ),
        download_chunk=DownloadChunk(
            sessions=downloads, storage=storage, audit=audit, clock=clock,
            session_ttl=ttl,
        ),
        finish_download=FinishDownload(
            sessions=downloads, audit=audit, clock=clock
        ),
        active_downloads=ListActiveDownloads(
            sessions=downloads, clock=clock, session_ttl=ttl
        ),
        tag_manifest=TagManifest(
            repos=repos, manifests=manifests, tags=tags, audit=audit,
            clock=clock,
        ),
        resolve=ResolveReference(repos=repos, manifests=manifests, tags=tags),
        list_tags=ListTags(repos=repos, tags=tags),
        delete_manifest=DeleteManifest(
            repos=repos, manifests=manifests, layers=layers, tags=tags,
            storage=storage, audit=audit, clock=clock,
        ),
        audit_events=ListAuditEvents(audit=audit),
        cleanup=CleanupExpiredSessions(
            uploads=uploads, downloads=downloads, storage=storage,
            audit=audit, clock=clock, session_ttl=ttl,
        ),
    )


def build_app(settings: Settings) -> FastAPI:
    """Build the FastAPI application with real dependencies.

    Args:
        settings: API settings.

    Returns:
        The ready to serve application.
    """
    return create_app(build_services(settings))


def bootstrap_admin(settings: Settings, nickname: str, password: str) -> int:
    """Create the first admin directly on the server machine.

    Args:
        settings: API settings.
        nickname: Login name of the admin.
        password: Password in plain text.

    Returns:
        Identifier of the new admin.

    Raises:
        Conflict: If an admin or the nickname already exists.
        InvalidInput: If the nickname or password are invalid.
    """
    return BootstrapAdmin(
        users=SQLiteUserRepository(_database(settings)),
        password_hasher=Pbkdf2PasswordHasher(settings.hash_iterations),
        pepper=settings.pepper,
    ).execute(nickname, password)
