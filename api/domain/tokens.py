from datetime import datetime

from api.data.models import UserToken
from api.domain.checksum import sha256_hex


def signature_of(raw_token: str) -> str:
    """Compute the stored signature of a raw token.

    Only this hash is stored, never the raw token.

    Args:
        raw_token: Token as sent by the client.

    Returns:
        SHA-256 of the token in hexadecimal.
    """
    return sha256_hex(raw_token.encode("utf-8"))


def is_active(token: UserToken, now: datetime) -> bool:
    """Check whether a token can still be used.

    Args:
        token: Stored token.
        now: Current moment.

    Returns:
        False if the token was revoked or has expired, True otherwise.
    """
    if token.revoked_at is not None:
        return False

    return token.expires_at is None or now < token.expires_at
