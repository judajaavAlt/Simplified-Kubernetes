from dataclasses import dataclass

from api.application.transfer_sessions import load_owned
from api.data.models import SessionStatus, User
from api.domain import chunking
from api.persistence.repository.upload_session import UploadSessionRepository


@dataclass
class UploadProgress:
    """Progress of an upload, used to resume it.

    Attributes:
        status: Current lifecycle state.
        received: Indexes of the received pieces, sorted.
        missing: Indexes of the pieces still missing.
    """

    status: SessionStatus
    received: list[int]
    missing: list[int]


@dataclass
class GetUploadStatus:
    """Tell the client which pieces are still missing, so it can resume.

    Attributes:
        sessions: Stores the transfer sessions.
    """

    sessions: UploadSessionRepository

    def execute(self, actor: User, upload_id: str) -> UploadProgress:
        """Report the progress of an upload of the actor.

        Args:
            actor: User that started the upload.
            upload_id: Upload session identifier.

        Returns:
            Status and received and missing pieces.

        Raises:
            NotFound: If the session does not exist.
            PermissionDenied: If the session belongs to another user.
        """
        session = load_owned(self.sessions, upload_id, actor)
        count = chunking.piece_count(session.total_size)

        return UploadProgress(
            status=session.status,
            received=sorted(session.received),
            missing=[i for i in range(count) if i not in session.received],
        )
