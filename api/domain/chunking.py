from api.domain.errors import InvalidInput


CHUNK_SIZE = 1024 * 1024
"""Every piece is 1 MB except the last one."""


def piece_count(total_size: int) -> int:
    """Count the pieces needed to store a blob.

    Args:
        total_size: Size of the blob in bytes.

    Returns:
        Number of pieces of at most ``CHUNK_SIZE`` bytes.
    """
    return -(-total_size // CHUNK_SIZE)


def piece_size(total_size: int, index: int) -> int:
    """Compute the expected size of one piece.

    Args:
        total_size: Size of the blob in bytes.
        index: Position of the piece, starting at 0.

    Returns:
        ``CHUNK_SIZE`` for every piece except the last one, which holds
        the remaining bytes.

    Raises:
        InvalidInput: If ``index`` is outside the blob.
    """
    if index < 0 or index >= piece_count(total_size):
        raise InvalidInput(f"Piece index out of range: {index}")

    return min(CHUNK_SIZE, total_size - index * CHUNK_SIZE)


def split(content: bytes) -> list[bytes]:
    """Split content into pieces of ``CHUNK_SIZE`` bytes.

    Args:
        content: Bytes to split.

    Returns:
        The pieces in order; the last one may be shorter.
    """
    return [
        content[start:start + CHUNK_SIZE]
        for start in range(0, len(content), CHUNK_SIZE)
    ]
