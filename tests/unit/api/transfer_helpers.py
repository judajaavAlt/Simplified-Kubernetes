"""Builds the transfer use cases over the in-memory World of conftest."""
from datetime import timedelta
from types import SimpleNamespace

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
from api.data.models import BlobKind
from api.domain import checksum, chunking


TTL = timedelta(hours=24)
MAX_SIZE = 10 * chunking.CHUNK_SIZE


def use_cases(w):
    return SimpleNamespace(
        start_upload=StartUpload(
            repos=w.repos,
            layers=w.layers,
            manifests=w.manifests,
            sessions=w.uploads,
            storage=w.storage,
            audit=w.audit,
            clock=w.clock,
            id_factory=w.new_id,
            max_size=MAX_SIZE,
        ),
        upload_chunk=UploadChunk(
            sessions=w.uploads,
            storage=w.storage,
            audit=w.audit,
            clock=w.clock,
            session_ttl=TTL,
        ),
        upload_status=GetUploadStatus(sessions=w.uploads),
        finish_upload=FinishUpload(
            sessions=w.uploads,
            storage=w.storage,
            layers=w.layers,
            manifests=w.manifests,
            audit=w.audit,
            clock=w.clock,
            session_ttl=TTL,
        ),
        cancel_upload=CancelUpload(
            sessions=w.uploads,
            storage=w.storage,
            audit=w.audit,
            clock=w.clock,
        ),
        start_download=StartDownload(
            repos=w.repos,
            layers=w.layers,
            manifests=w.manifests,
            storage=w.storage,
            sessions=w.downloads,
            audit=w.audit,
            clock=w.clock,
            id_factory=w.new_id,
        ),
        download_chunk=DownloadChunk(
            sessions=w.downloads,
            storage=w.storage,
            audit=w.audit,
            clock=w.clock,
            session_ttl=TTL,
        ),
        finish_download=FinishDownload(
            sessions=w.downloads, audit=w.audit, clock=w.clock
        ),
        active_downloads=ListActiveDownloads(
            sessions=w.downloads, clock=w.clock, session_ttl=TTL
        ),
        tag_manifest=TagManifest(
            repos=w.repos,
            manifests=w.manifests,
            tags=w.tags,
            audit=w.audit,
            clock=w.clock,
        ),
        resolve=ResolveReference(
            repos=w.repos, manifests=w.manifests, tags=w.tags
        ),
        list_tags=ListTags(repos=w.repos, tags=w.tags),
        delete_manifest=DeleteManifest(
            repos=w.repos,
            manifests=w.manifests,
            layers=w.layers,
            tags=w.tags,
            storage=w.storage,
            audit=w.audit,
            clock=w.clock,
        ),
        cleanup=CleanupExpiredSessions(
            uploads=w.uploads,
            downloads=w.downloads,
            storage=w.storage,
            audit=w.audit,
            clock=w.clock,
            session_ttl=TTL,
        ),
    )


def push(w, actor, content, repository="org/app",
         kind=BlobKind.LAYER, layers=None) -> str:
    """Upload a whole blob through Start -> Chunk* -> Finish."""
    uc = use_cases(w)
    signature = checksum.sha256_hex(content)

    ticket = uc.start_upload.execute(
        actor, repository, kind, signature, len(content), layers
    )

    if ticket.status == "exists":
        return signature

    for index, piece in enumerate(chunking.split(content)):
        uc.upload_chunk.execute(
            actor, ticket.upload_id, index,
            checksum.sha256_hex(piece), piece,
        )

    return uc.finish_upload.execute(actor, ticket.upload_id)
