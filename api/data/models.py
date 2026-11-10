from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    """Role of a user inside the organization that owns the API.

    Attributes:
        ADMIN: Manages users and can do every registry operation.
        DEVOPS: Publishes and deletes templates.
        DEVELOPER: Can only download templates.
    """

    ADMIN = "admin"
    DEVOPS = "devops"
    DEVELOPER = "developer"


class BlobKind(str, Enum):
    """Kind of content stored as a blob.

    Attributes:
        LAYER: A tarball with part of the template files.
        MANIFEST: The YAML that lists the layers and variables of a template.
    """

    LAYER = "layer"
    MANIFEST = "manifest"


class SessionStatus(str, Enum):
    """Lifecycle state of an upload or download session.

    Attributes:
        OPEN: The session accepts chunks.
        COMPLETED: The transfer finished and was verified.
        FAILED: The final checksum did not match.
        CANCELLED: The client cancelled the transfer.
        EXPIRED: The session was inactive longer than its time to live.
    """

    OPEN = "open"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class User:
    """Account that can authenticate against the API.

    Attributes:
        id: Database identifier.
        nickname: Unique login name.
        password: PBKDF2 hash of the password, never the raw value.
        salt: Random salt used to compute ``password``.
        role: Role that decides the allowed actions.
        must_change_password: True until the user replaces the initial
            password; while True no tokens are issued.
    """

    id: int
    nickname: str
    password: str
    salt: str
    role: Role
    must_change_password: bool = True


@dataclass
class UserToken:
    """Bearer token issued to a user.

    Only the SHA-256 of the raw token is stored.

    Attributes:
        signature: SHA-256 of the raw token.
        user_id: Owner of the token.
        created_at: Moment the token was issued.
        expires_at: Expiration moment, or None if it never expires.
        revoked_at: Moment the token was revoked, or None if it is active.
    """

    signature: str
    user_id: int
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass
class Repo:
    """Template repository, named ``<organization>/<repo>``.

    Attributes:
        id: Database identifier.
        name: Repository name in lowercase.
    """

    id: int
    name: str


@dataclass
class Layer:
    """Layer blob registered in a repository.

    Attributes:
        signature: SHA-256 of the layer content.
        repo_id: Repository that references the layer.
    """

    signature: str
    repo_id: int


@dataclass
class Manifest:
    """Manifest blob registered in a repository.

    Attributes:
        signature: SHA-256 of the manifest content.
        repo_id: Repository that owns the manifest.
        layers: Signatures of the layers the manifest references.
    """

    signature: str
    repo_id: int
    layers: list[str] = field(default_factory=list)


@dataclass
class Tag:
    """Human readable name that points to a manifest.

    Attributes:
        manifest_signature: SHA-256 of the tagged manifest.
        repo_id: Repository of the tag.
        tag: Tag name, for example ``latest``.
    """

    manifest_signature: str
    repo_id: int
    tag: str


@dataclass
class PieceInfo:
    """One piece of a stored blob.

    Attributes:
        index: Position of the piece, starting at 0.
        signature: SHA-256 of the piece content.
        size: Size of the piece in bytes.
    """

    index: int
    signature: str
    size: int


@dataclass
class BlobMetadata:
    """Description of a stored blob and its pieces.

    Attributes:
        signature: SHA-256 of the whole blob.
        total_size: Size of the blob in bytes.
        chunk_size: Size of every piece except the last one.
        pieces: Pieces in order.
    """

    signature: str
    total_size: int
    chunk_size: int
    pieces: list[PieceInfo]


@dataclass
class UploadSession:
    """State of a blob upload in progress.

    Attributes:
        id: Random session identifier sent to the client.
        user_id: User that started the upload.
        repo_id: Destination repository.
        kind: Whether the blob is a layer or a manifest.
        blob_signature: Declared SHA-256 of the whole blob.
        total_size: Declared size of the blob in bytes.
        created_at: Moment the session started.
        last_activity: Moment of the last accepted request.
        layers: For a manifest, the signatures of its layers.
        received: Signature of every received piece, by index.
        status: Current lifecycle state.
    """

    id: str
    user_id: int
    repo_id: int
    kind: BlobKind
    blob_signature: str
    total_size: int
    created_at: datetime
    last_activity: datetime
    layers: list[str] = field(default_factory=list)
    received: dict[int, str] = field(default_factory=dict)
    status: SessionStatus = SessionStatus.OPEN


@dataclass
class DownloadSession:
    """State of a blob download in progress.

    Attributes:
        id: Random session identifier sent to the client.
        user_id: User that started the download.
        repo_id: Repository the blob belongs to.
        blob_signature: SHA-256 of the blob being downloaded.
        created_at: Moment the session started.
        last_activity: Moment of the last request.
        status: Current lifecycle state.
    """

    id: str
    user_id: int
    repo_id: int
    blob_signature: str
    created_at: datetime
    last_activity: datetime
    status: SessionStatus = SessionStatus.OPEN


@dataclass
class AuditEvent:
    """Entry of the audit log.

    Attributes:
        user_id: User that performed the action.
        session_id: Related transfer session, if any.
        event: Name of the action, for example ``upload.finish``.
        result: Outcome of the action, for example ``ok`` or ``denied``.
        created_at: Moment of the action.
        detail: Free text with extra information.
    """

    user_id: int
    session_id: str | None
    event: str
    result: str
    created_at: datetime
    detail: str = ""
