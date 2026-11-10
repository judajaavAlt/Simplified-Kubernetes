from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import secrets

from api.application.audit import record
from api.application.registry.lookup import find_repo
from api.data.models import BlobMetadata, DownloadSession, User
from api.domain import checksum, permissions
from api.domain.errors import InvalidInput, NotFound
from api.domain.permissions import Action
from api.persistence.blob_storage import BlobStorage
from api.persistence.repository.audit_log import AuditLogRepository
from api.persistence.repository.download_session import (
    DownloadSessionRepository,
)
from api.persistence.repository.layer import LayerRepository
from api.persistence.repository.manifest import ManifestRepository
from api.persistence.repository.repo import RepoRepository


def _new_session_id() -> str:
    """Create a random session identifier.

    Returns:
        A URL safe random string.
    """
    return secrets.token_urlsafe(24)


@dataclass
class DownloadTicket:
    """Answer to the start of a download.

    Attributes:
        download_id: Session identifier.
        metadata: Size and ordered pieces of the blob.
    """

    download_id: str
    metadata: BlobMetadata


@dataclass
class StartDownload:
    """Handshake: open a download and hand out the piece list.

    Attributes:
        repos: Stores the repositories.
        layers: Registers the layers of each repository.
        manifests: Registers the manifests of each repository.
        storage: Stores the blobs and the staged pieces.
        sessions: Stores the transfer sessions.
        audit: Receives the audit events.
        clock: Returns the current moment.
        id_factory: Creates random session identifiers.
    """

    repos: RepoRepository
    layers: LayerRepository
    manifests: ManifestRepository
    storage: BlobStorage
    sessions: DownloadSessionRepository
    audit: AuditLogRepository
    clock: Callable[[], datetime]
    id_factory: Callable[[], str] = _new_session_id

    def execute(
        self, actor: User, repository: str, signature: str
    ) -> DownloadTicket:
        """Open a download session for a blob of a repository.

        Args:
            actor: User making the request.
            repository: Repository name, ``<organization>/<repo>``.
            signature: SHA-256 of the layer or manifest.

        Returns:
            The session identifier and the blob metadata.

        Raises:
            PermissionDenied: If the role cannot pull.
            InvalidInput: If the signature is not a SHA-256.
            NotFound: If the repository or the blob do not exist.
        """
        permissions.require(actor.role, Action.PULL)

        if not checksum.is_sha256_hex(signature):
            raise InvalidInput("Expected a lowercase SHA-256 hex digest")

        repo = find_repo(self.repos, repository)

        if (
            self.layers.get(signature, repo.id) is None
            and self.manifests.get(signature, repo.id) is None
        ):
            raise NotFound("The blob is not in the repository")

        metadata = self.storage.read_metadata(signature)

        if metadata is None:
            raise NotFound("The blob is not stored")

        now = self.clock()
        session = DownloadSession(
            id=self.id_factory(),
            user_id=actor.id,
            repo_id=repo.id,
            blob_signature=signature,
            created_at=now,
            last_activity=now,
        )
        self.sessions.create(session)

        record(self.audit, self.clock, actor.id, session.id,
               "download.start", "started", signature)

        return DownloadTicket(download_id=session.id, metadata=metadata)
