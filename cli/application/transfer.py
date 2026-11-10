"""Blob transfer in pieces with SHA-256 checks and retries."""
import hashlib
from collections.abc import Callable

from cli.domain.errors import ChecksumRejectedError, RegistryError
from cli.domain.ports import RegistryClient


MAX_ATTEMPTS = 3

Report = Callable[[str], None]


def upload_blob(
    client: RegistryClient,
    repository: str,
    kind: str,
    signature: str,
    content: bytes,
    layers: tuple[str, ...],
    report: Report,
) -> bool:
    """Upload a blob piece by piece, one piece at a time.

    A piece the registry rejects is sent again up to ``MAX_ATTEMPTS``
    times; after that, or on any other error, the upload is cancelled.

    Args:
        client: Authenticated registry client.
        repository: ``organization/repo``.
        kind: ``layer`` or ``manifest``.
        signature: SHA-256 of the blob.
        content: Bytes of the blob.
        layers: For a manifest, its layers.
        report: Receives progress messages.

    Returns:
        True if it was uploaded, False if the registry already had it.

    Raises:
        RegistryError: If the upload fails.
    """
    ticket = client.start_upload(repository, kind, signature, len(content), layers)
    if ticket.status == "exists":
        return False
    try:
        size = ticket.chunk_size
        for index in range(ticket.pieces):
            piece = content[index * size:(index + 1) * size]
            piece_signature = _sha256(piece)
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    client.upload_chunk(ticket.upload_id, index,
                                        piece_signature, piece)
                    break
                except ChecksumRejectedError:
                    if attempt == MAX_ATTEMPTS:
                        raise
            report(f"piece {index + 1}/{ticket.pieces}")
        if client.finish_upload(ticket.upload_id) != signature:
            raise RegistryError("The registry stored a different blob")
    except Exception:
        try:
            client.cancel_upload(ticket.upload_id)
        except RegistryError:
            pass
        raise
    return True


def download_blob(
    client: RegistryClient, repository: str, signature: str, report: Report
) -> bytes:
    """Download a blob piece by piece, verifying every piece and the whole.

    A corrupted piece is downloaded again up to ``MAX_ATTEMPTS`` times.

    Args:
        client: Authenticated registry client.
        repository: ``organization/repo``.
        signature: SHA-256 of the blob.
        report: Receives progress messages.

    Returns:
        The verified bytes.

    Raises:
        RegistryError: If a piece or the whole blob cannot be verified.
    """
    ticket = client.start_download(repository, signature)
    parts = []
    for piece in ticket.pieces:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            content = client.download_chunk(ticket.download_id, piece.index)
            if _sha256(content) == piece.signature:
                break
            if attempt == MAX_ATTEMPTS:
                client.finish_download(ticket.download_id, "0" * 64)
                raise RegistryError(
                    f"Piece {piece.index} of {signature[:12]} is corrupted"
                )
        parts.append(content)
        report(f"piece {piece.index + 1}/{len(ticket.pieces)}")
    content = b"".join(parts)
    rebuilt = _sha256(content)
    client.finish_download(ticket.download_id, rebuilt)
    if rebuilt != signature:
        raise RegistryError(f"Blob {signature[:12]} does not match its SHA-256")
    return content


def _sha256(content: bytes) -> str:
    """Compute the SHA-256 of some content.

    Args:
        content: Bytes to hash.

    Returns:
        The digest in hexadecimal.
    """
    return hashlib.sha256(content).hexdigest()
