from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import secrets

from api.application.audit import record
from api.application.upload.registration import register_blob
from api.data.models import BlobKind, Repo, UploadSession, User
from api.domain import checksum, chunking, naming, permissions
from api.domain.errors import InvalidInput, NotFound
from api.domain.permissions import Action
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.layer import LayerRepository
from api.persistence.repository.manifest import ManifestRepository
from api.persistence.repository.repo import RepoRepository
from api.persistence.repository.upload_session import UploadSessionRepository


def _new_session_id() -> str:
    """Create a random session identifier.

    Returns:
        A URL safe random string.
    """
    return secrets.token_urlsafe(24)


@dataclass
class UploadTicket:
    """Answer to the start of an upload.

    Attributes:
        status: ``started`` if pieces must be sent, or ``exists`` if the
            blob was already stored and nothing must be sent.
        upload_id: Session identifier, or None when ``status`` is
            ``exists``.
        pieces: Number of pieces to send.
    """

    status: str  # "started" or "exists"
    upload_id: str | None
    pieces: int


@dataclass
class StartUpload:
    """Handshake: the client announces the blob it is going to send.

    Attributes:
        repos: Stores the repositories.
        layers: Registers the layers of each repository.
        manifests: Registers the manifests of each repository.
        sessions: Stores the transfer sessions.
        storage: Stores the blobs and the staged pieces.
        audit: Receives the audit events.
        clock: Returns the current moment.
        max_size: Largest accepted blob, in bytes.
        id_factory: Creates random session identifiers.
    """

    repos: RepoRepository
    layers: LayerRepository
    manifests: ManifestRepository
    sessions: UploadSessionRepository
    storage: BlobStorage
    audit: AuditLogRepository
    clock: Callable[[], datetime]
    max_size: int
    id_factory: Callable[[], str] = _new_session_id

    def execute(
        self,
        actor: User,
        repository: str,
        kind: BlobKind,
        signature: str,
        size: int,
        layers: list[str] | None = None,
    ) -> UploadTicket:
        """Open an upload session, or skip it if the blob is already stored.

        The repository is created on its first upload. Like Docker, a blob
        that is already stored is only registered, never sent again.

        Args:
            actor: User making the request.
            repository: Destination repository, ``<organization>/<repo>``.
            kind: Whether the blob is a layer or a manifest.
            signature: SHA-256 of the whole blob.
            size: Size of the blob in bytes.
            layers: For a manifest, the signatures of its layers, which must
                already be in the repository.

        Returns:
            The ticket that tells the client what to send.

        Raises:
            PermissionDenied: If the role cannot push.
            InvalidInput: If the repository, signature, size or layers are
                invalid.
            NotFound: If the manifest references layers the repository lacks.
        """
        permissions.require(actor.role, Action.PUSH)
        naming.validate_repository(repository)
        kind = BlobKind(kind)
        layers = list(layers or [])

        if not checksum.is_sha256_hex(signature):
            raise InvalidInput("Expected a lowercase SHA-256 hex digest")

        if size < 0 or size > self.max_size:
            raise InvalidInput("Invalid upload size")

        if kind is BlobKind.LAYER and layers:
            raise InvalidInput("A layer cannot depend on other layers")

        if not all(checksum.is_sha256_hex(layer) for layer in layers):
            raise InvalidInput("Every layer must be a SHA-256 hex digest")

        repo = self.repos.get_by_name(repository)

        if layers and (
            repo is None
            or any(self.layers.get(layer, repo.id) is None for layer in layers)
        ):
            raise NotFound("The manifest needs layers the repository lacks")

        repo_id = repo.id if repo else self.repos.create(
            Repo(id=0, name=repository)
        )

        # Like Docker: a blob already stored is never sent again.
        if self.storage.exists(signature):
            register_blob(
                self.layers, self.manifests, kind, signature, repo_id, layers
            )
            record(self.audit, self.clock, actor.id, None,
                   "upload.start", "exists", signature)
            return UploadTicket(status="exists", upload_id=None, pieces=0)

        now = self.clock()
        session = UploadSession(
            id=self.id_factory(),
            user_id=actor.id,
            repo_id=repo_id,
            kind=kind,
            blob_signature=signature,
            total_size=size,
            created_at=now,
            last_activity=now,
            layers=layers,
        )
        self.sessions.create(session)

        record(self.audit, self.clock, actor.id, session.id,
               "upload.start", "started", signature)

        return UploadTicket(
            status="started",
            upload_id=session.id,
            pieces=chunking.piece_count(size),
        )
