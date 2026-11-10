import hashlib
import hmac
import re
from collections.abc import Iterable


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def sha256_hex(content: bytes) -> str:
    """Compute the SHA-256 of some content.

    Args:
        content: Bytes to hash.

    Returns:
        The digest as 64 lowercase hexadecimal characters.
    """
    return hashlib.sha256(content).hexdigest()


def sha256_of_parts(parts: Iterable[bytes]) -> str:
    """Compute the SHA-256 of the concatenation of several parts.

    The parts are hashed one by one, so they are never joined in memory.

    Args:
        parts: Byte strings in order.

    Returns:
        The digest as 64 lowercase hexadecimal characters.
    """
    digest = hashlib.sha256()

    for part in parts:
        digest.update(part)

    return digest.hexdigest()


def is_sha256_hex(value) -> bool:
    """Check whether a value looks like a SHA-256 signature.

    Args:
        value: Any value.

    Returns:
        True if ``value`` is a string of 64 lowercase hexadecimal
        characters.
    """
    return isinstance(value, str) and bool(_SHA256_HEX.match(value))


def same_signature(a: str, b: str) -> bool:
    """Compare two signatures in constant time.

    Args:
        a: First signature.
        b: Second signature.

    Returns:
        True if both signatures are equal.
    """
    return hmac.compare_digest(a, b)


def matches(content: bytes, signature: str) -> bool:
    """Check whether some content has the expected signature.

    Args:
        content: Bytes to verify.
        signature: Expected SHA-256 in hexadecimal.

    Returns:
        True if the SHA-256 of ``content`` equals ``signature``.
    """
    return same_signature(sha256_hex(content), signature)
