from fastapi import Depends, Header, Request

from api.data.models import User
from api.domain.chunking import CHUNK_SIZE
from api.domain.errors import AuthenticationError
from api.presentation.errors import PayloadTooLarge
from api.presentation.services import ApiServices


def get_services(request: Request) -> ApiServices:
    """Return the use cases stored in the application state.

    Args:
        request: Current HTTP request.

    Returns:
        The use cases built by the composition root.
    """
    return request.app.state.services


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    """Extract the bearer token from the ``Authorization`` header.

    Args:
        authorization: Value of the ``Authorization`` header.

    Returns:
        The raw token.

    Raises:
        AuthenticationError: If the header is missing or is not
            ``Bearer <token>``.
    """
    scheme, _, token = (authorization or "").partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Missing bearer token")

    return token


def current_user(
    token: str = Depends(bearer_token),
    services: ApiServices = Depends(get_services),
) -> User:
    """Resolve the user that owns the request token.

    Args:
        token: Raw bearer token.
        services: Use cases.

    Returns:
        The authenticated user.

    Raises:
        AuthenticationError: If the token is not valid.
        PasswordChangeRequired: If the user must change the password.
    """
    return services.validate_token.execute(token)


async def read_chunk_body(request: Request) -> bytes:
    """Read the raw body, refusing anything bigger than one piece.

    Args:
        request: Current HTTP request.

    Returns:
        The body bytes.

    Raises:
        PayloadTooLarge: If the body is bigger than ``CHUNK_SIZE``.
    """
    declared = request.headers.get("content-length")

    if declared is not None and int(declared) > CHUNK_SIZE:
        raise PayloadTooLarge(f"A chunk cannot exceed {CHUNK_SIZE} bytes")

    body = bytearray()

    async for part in request.stream():
        body.extend(part)

        if len(body) > CHUNK_SIZE:
            raise PayloadTooLarge(f"A chunk cannot exceed {CHUNK_SIZE} bytes")

    return bytes(body)
