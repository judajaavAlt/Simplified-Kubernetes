from dataclasses import dataclass

from api.application.admin.list_audit_events import ListAuditEvents
from api.application.auth.authenticate_user import AuthenticateUser
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


@dataclass
class ApiServices:
    """Every use case the HTTP layer can call.

    The composition root in infraestructure builds it with the real
    implementations; tests can build it with fakes. Each attribute is the
    use case of the same name.
    """

    authenticate: AuthenticateUser
    change_password: ChangePassword
    validate_token: ValidateToken
    revoke_token: RevokeToken
    create_user: CreateUser
    start_upload: StartUpload
    upload_chunk: UploadChunk
    upload_status: GetUploadStatus
    finish_upload: FinishUpload
    cancel_upload: CancelUpload
    start_download: StartDownload
    download_chunk: DownloadChunk
    finish_download: FinishDownload
    active_downloads: ListActiveDownloads
    tag_manifest: TagManifest
    resolve: ResolveReference
    list_tags: ListTags
    delete_manifest: DeleteManifest
    audit_events: ListAuditEvents
    cleanup: CleanupExpiredSessions
