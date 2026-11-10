from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.domain.errors import (
    AuthenticationError,
    ChecksumMismatch,
    Conflict,
    DomainError,
    InvalidInput,
    NotFound,
    PasswordChangeRequired,
    PermissionDenied,
)


class PayloadTooLarge(Exception):
    """The HTTP body is bigger than what the endpoint accepts."""


# (status code, stable error code the CLI can rely on)
_ERRORS = {
    AuthenticationError: (401, "authentication_error"),
    PasswordChangeRequired: (403, "password_change_required"),
    PermissionDenied: (403, "permission_denied"),
    NotFound: (404, "not_found"),
    Conflict: (409, "conflict"),
    ChecksumMismatch: (422, "checksum_mismatch"),
    InvalidInput: (422, "invalid_input"),
}


def _body(code: str, detail: str) -> dict:
    """Build the JSON body of an error response.

    Args:
        code: Stable error code the CLI can rely on.
        detail: Human readable message.

    Returns:
        ``{"error": code, "detail": detail}``.
    """
    return {"error": code, "detail": detail}


async def _domain_error(request: Request, error: DomainError) -> JSONResponse:
    """Translate a business rule violation into an HTTP response.

    Args:
        request: Request that failed.
        error: The violation.

    Returns:
        A JSON response with the status code of the error type
        (401, 403, 404, 409 or 422; 400 for unknown types).
    """
    status, code = _ERRORS.get(type(error), (400, "domain_error"))
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None

    return JSONResponse(_body(code, str(error)), status, headers=headers)


async def _too_large(request: Request, error: PayloadTooLarge) -> JSONResponse:
    """Translate a too large body into a 413 response.

    Args:
        request: Request that failed.
        error: The error.

    Returns:
        A JSON response with status 413.
    """
    return JSONResponse(_body("payload_too_large", str(error)), 413)


def register_error_handlers(app: FastAPI) -> None:
    """Register the error translations in an application.

    Args:
        app: FastAPI application.
    """
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(PayloadTooLarge, _too_large)
