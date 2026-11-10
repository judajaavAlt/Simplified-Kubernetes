from fastapi import APIRouter, Depends, Response

from api.data.models import User
from api.presentation.dependencies import current_user, get_services
from api.presentation.schemas import (
    ActiveDownload,
    ActiveDownloadsResponse,
    DownloadTicketResponse,
    FinishDownloadRequest,
    FinishDownloadResponse,
    PieceSchema,
    StartDownloadRequest,
)
from api.presentation.services import ApiServices


router = APIRouter(prefix="/downloads", tags=["downloads"])


@router.post("", response_model=DownloadTicketResponse)
def start_download(
    body: StartDownloadRequest,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Open a download and return the list of pieces.

    Args:
        body: Repository and blob signature.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The session identifier and the blob metadata.
    """
    ticket = services.start_download.execute(
        user, body.repository, body.signature
    )
    metadata = ticket.metadata

    return DownloadTicketResponse(
        download_id=ticket.download_id,
        signature=metadata.signature,
        total_size=metadata.total_size,
        chunk_size=metadata.chunk_size,
        pieces=[
            PieceSchema(index=p.index, signature=p.signature, size=p.size)
            for p in metadata.pieces
        ],
    )


@router.get("/{download_id}/chunks/{index}")
def download_chunk(
    download_id: str,
    index: int,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Return one piece as raw bytes.

    Args:
        download_id: Download session identifier.
        index: Position of the piece, starting at 0.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The bytes, with the piece SHA-256 in ``X-Chunk-Sha256`` and the
        index in ``X-Chunk-Index``.
    """
    piece = services.download_chunk.execute(user, download_id, index)

    return Response(
        content=piece.content,
        media_type="application/octet-stream",
        headers={
            "X-Chunk-Sha256": piece.signature,
            "X-Chunk-Index": str(piece.index),
        },
    )


@router.post("/{download_id}/finish", response_model=FinishDownloadResponse)
def finish_download(
    download_id: str,
    body: FinishDownloadRequest,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Report the SHA-256 the client rebuilt and close the download.

    Args:
        download_id: Download session identifier.
        body: Rebuilt signature.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        Whether the download completed correctly.
    """
    completed = services.finish_download.execute(
        user, download_id, body.signature
    )
    return FinishDownloadResponse(completed=completed)


@router.get("", response_model=ActiveDownloadsResponse)
def active_downloads(
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """List the downloads in progress (admin only).

    Args:
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The active downloads.
    """
    return ActiveDownloadsResponse(
        downloads=[
            ActiveDownload(
                download_id=s.id,
                user_id=s.user_id,
                repo_id=s.repo_id,
                signature=s.blob_signature,
                started_at=s.created_at,
                last_activity=s.last_activity,
            )
            for s in services.active_downloads.execute(user)
        ]
    )
