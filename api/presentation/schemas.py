from datetime import datetime

from pydantic import BaseModel

from api.data.models import BlobKind, Role


# Auth and users -----------------------------------------------------

class TokenRequest(BaseModel):
    """Credentials to get a token.

    Attributes:
        nickname: Login name.
        password: Password in plain text.
    """

    nickname: str
    password: str


class TokenResponse(BaseModel):
    """A newly issued token.

    Attributes:
        token: Raw bearer token.
    """

    token: str


class ChangePasswordRequest(BaseModel):
    """Data to change a password.

    Attributes:
        nickname: Login name.
        current_password: Password in use.
        new_password: Password that replaces it.
    """

    nickname: str
    current_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    """Data of a new user.

    Attributes:
        nickname: Login name.
        password: Temporary password.
        role: Role of the user.
    """

    nickname: str
    password: str
    role: Role


class CreatedUserResponse(BaseModel):
    """A newly created user.

    Attributes:
        id: User identifier.
    """

    id: int


# Uploads ------------------------------------------------------------

class StartUploadRequest(BaseModel):
    """Announcement of a blob to upload.

    Attributes:
        repository: Destination repository, ``<organization>/<repo>``.
        kind: ``layer`` or ``manifest``.
        signature: SHA-256 of the blob.
        size: Size of the blob in bytes.
        layers: For a manifest, the signatures of its layers.
    """

    repository: str
    kind: BlobKind
    signature: str
    size: int
    layers: list[str] = []


class UploadTicketResponse(BaseModel):
    """Answer to the start of an upload.

    Attributes:
        status: ``started`` or ``exists``.
        upload_id: Session identifier, or None if the blob already exists.
        pieces: Number of pieces to send.
        chunk_size: Size of every piece but the last.
    """

    status: str
    upload_id: str | None
    pieces: int
    chunk_size: int


class UploadStatusResponse(BaseModel):
    """Progress of an upload.

    Attributes:
        status: Session status.
        received: Indexes of the received pieces.
        missing: Indexes still missing.
    """

    status: str
    received: list[int]
    missing: list[int]


class FinishUploadResponse(BaseModel):
    """A stored blob.

    Attributes:
        signature: SHA-256 of the blob.
    """

    signature: str


# Downloads ----------------------------------------------------------

class StartDownloadRequest(BaseModel):
    """Request to download a blob.

    Attributes:
        repository: Repository, ``<organization>/<repo>``.
        signature: SHA-256 of the layer or manifest.
    """

    repository: str
    signature: str


class PieceSchema(BaseModel):
    """One piece of a blob.

    Attributes:
        index: Position, starting at 0.
        signature: SHA-256 of the piece.
        size: Size in bytes.
    """

    index: int
    signature: str
    size: int


class DownloadTicketResponse(BaseModel):
    """Answer to the start of a download.

    Attributes:
        download_id: Session identifier.
        signature: SHA-256 of the blob.
        total_size: Size of the blob in bytes.
        chunk_size: Size of every piece but the last.
        pieces: Pieces in order.
    """

    download_id: str
    signature: str
    total_size: int
    chunk_size: int
    pieces: list[PieceSchema]


class FinishDownloadRequest(BaseModel):
    """Result computed by the client.

    Attributes:
        signature: SHA-256 of the rebuilt blob.
    """

    signature: str


class FinishDownloadResponse(BaseModel):
    """Outcome of a download.

    Attributes:
        completed: True if the signature matched.
    """

    completed: bool


class ActiveDownload(BaseModel):
    """A download in progress.

    Attributes:
        download_id: Session identifier.
        user_id: User downloading.
        repo_id: Repository identifier.
        signature: SHA-256 of the blob.
        started_at: Start moment.
        last_activity: Moment of the last request.
    """

    download_id: str
    user_id: int
    repo_id: int
    signature: str
    started_at: datetime
    last_activity: datetime


class ActiveDownloadsResponse(BaseModel):
    """Downloads in progress.

    Attributes:
        downloads: The active downloads.
    """

    downloads: list[ActiveDownload]


# Registry -----------------------------------------------------------

class TagRequest(BaseModel):
    """Request to point a tag to a manifest.

    Attributes:
        repository: Repository, ``<organization>/<repo>``.
        tag: Tag name.
        manifest: SHA-256 of the manifest.
    """

    repository: str
    tag: str
    manifest: str


class ResolvedManifestResponse(BaseModel):
    """A resolved manifest.

    Attributes:
        signature: SHA-256 of the manifest.
        layers: Signatures of its layers, in order.
    """

    signature: str
    layers: list[str]


class TagItem(BaseModel):
    """One tag.

    Attributes:
        tag: Tag name.
        manifest: SHA-256 of the manifest.
    """

    tag: str
    manifest: str


class TagsResponse(BaseModel):
    """Tags of a repository.

    Attributes:
        tags: The tags.
    """

    tags: list[TagItem]


class DeletedResponse(BaseModel):
    """A deleted manifest.

    Attributes:
        deleted: SHA-256 of the manifest.
    """

    deleted: str


# Admin --------------------------------------------------------------

class AuditItem(BaseModel):
    """One audit event.

    Attributes:
        user_id: User that acted.
        session_id: Related transfer session, if any.
        event: Name of the action.
        result: Outcome.
        detail: Extra information.
        created_at: Moment of the action.
    """

    user_id: int
    session_id: str | None
    event: str
    result: str
    detail: str
    created_at: datetime


class AuditResponse(BaseModel):
    """Recent audit events.

    Attributes:
        events: The events, newest first.
    """

    events: list[AuditItem]


class CleanupResponse(BaseModel):
    """Result of a cleanup.

    Attributes:
        expired: Number of sessions expired.
    """

    expired: int
