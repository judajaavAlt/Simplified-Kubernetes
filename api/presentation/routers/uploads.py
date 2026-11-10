from fastapi import APIRouter, Depends, Header, status
from starlette.concurrency import run_in_threadpool

from api.data.models import User
from api.domain.chunking import CHUNK_SIZE
from api.presentation.dependencies import (
    current_user,
    get_services,
    read_chunk_body,
)
from api.presentation.schemas import (
    FinishUploadResponse,
    StartUploadRequest,
    UploadStatusResponse,
    UploadTicketResponse,
)
from api.presentation.services import ApiServices


router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=UploadTicketResponse)
def start_upload(
    body: StartUploadRequest,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Announce a blob and open an upload if it is not stored yet.

    Args:
        body: Repository, kind, signature, size and layers.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The upload ticket.
    """
    ticket = services.start_upload.execute(
        user, body.repository, body.kind, body.signature, body.size,
        body.layers,
    )
    return UploadTicketResponse(
        status=ticket.status,
        upload_id=ticket.upload_id,
        pieces=ticket.pieces,
        chunk_size=CHUNK_SIZE,
    )


@router.put(
    "/{upload_id}/chunks/{index}", status_code=status.HTTP_204_NO_CONTENT
)
async def upload_chunk(
    upload_id: str,
    index: int,
    x_chunk_sha256: str = Header(),
    content: bytes = Depends(read_chunk_body),
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Receive one piece as the raw request body.

    Args:
        upload_id: Upload session identifier.
        index: Position of the piece, starting at 0.
        x_chunk_sha256: SHA-256 of the piece, from the ``X-Chunk-Sha256``
            header.
        content: Raw body, at most one piece.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.
    """
    await run_in_threadpool(
        services.upload_chunk.execute,
        user, upload_id, index, x_chunk_sha256, content,
    )


@router.get("/{upload_id}", response_model=UploadStatusResponse)
def upload_status(
    upload_id: str,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Report which pieces were received and which are missing.

    Args:
        upload_id: Upload session identifier.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The progress of the upload.
    """
    progress = services.upload_status.execute(user, upload_id)
    return UploadStatusResponse(
        status=progress.status.value,
        received=progress.received,
        missing=progress.missing,
    )


@router.post("/{upload_id}/finish", response_model=FinishUploadResponse)
def finish_upload(
    upload_id: str,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Verify the whole blob and store it.

    Args:
        upload_id: Upload session identifier.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.

    Returns:
        The signature of the stored blob.
    """
    signature = services.finish_upload.execute(user, upload_id)
    return FinishUploadResponse(signature=signature)


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_upload(
    upload_id: str,
    user: User = Depends(current_user),
    services: ApiServices = Depends(get_services),
):
    """Cancel an upload and discard its pieces.

    Args:
        upload_id: Upload session identifier.
        user: Authenticated user, injected by FastAPI.
        services: Use cases, injected by FastAPI.
    """
    services.cancel_upload.execute(user, upload_id)
