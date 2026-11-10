"""Paths inside layers, always relative and with ``/`` separators."""
from pathlib import PurePosixPath

from cli.domain.errors import ValidationError


def join(objective: str, relative: str) -> str:
    """Place a path inside the objective folder of a layer (C-14).

    Args:
        objective: Folder of the layer; ``.`` or empty means the root.
        relative: Path relative to the origin of the layer.

    Returns:
        The normalized path.
    """
    joined = PurePosixPath(objective.replace("\\", "/"), relative)
    return "/".join(part for part in joined.parts if part not in (".", ""))


def check_relative(path: str) -> str:
    """Ensure a path cannot escape the destination folder.

    Args:
        path: Path from a layer.

    Returns:
        The same path.

    Raises:
        ValidationError: If the path is absolute, has a drive or uses
            ``..``.
    """
    normalized = path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if normalized.startswith("/") or (parts and ":" in parts[0]) or ".." in parts:
        raise ValidationError(f"Unsafe path in template: '{path}'")
    return path
