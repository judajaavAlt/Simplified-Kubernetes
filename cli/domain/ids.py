"""Template IDs: the SHA-256 of the manifest (C-10, C-20)."""
import re


MIN_PREFIX = 4
SHORT_LENGTH = 12

_HEX = re.compile(r"^[0-9a-f]+$")


def is_id(text: str) -> bool:
    """Check whether a text is a complete ID.

    Args:
        text: Text to check.

    Returns:
        True for 64 lowercase hexadecimal characters.
    """
    return len(text) == 64 and bool(_HEX.match(text))


def is_id_prefix(text: str) -> bool:
    """Check whether a text can be the start of an ID.

    Args:
        text: Text to check.

    Returns:
        True for 4 to 64 lowercase hexadecimal characters.
    """
    return MIN_PREFIX <= len(text) <= 64 and bool(_HEX.match(text))


def short(template_id: str) -> str:
    """Shorten an ID for display, like Docker.

    Args:
        template_id: Complete ID.

    Returns:
        Its first 12 characters.
    """
    return template_id[:SHORT_LENGTH]
