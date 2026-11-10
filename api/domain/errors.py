class DomainError(Exception):
    """Base class for every business rule violation."""


class InvalidInput(DomainError):
    """The request data breaks a validation rule."""


class NotFound(DomainError):
    """The requested resource does not exist."""


class Conflict(DomainError):
    """The resource is in a state that does not allow the operation."""


class PermissionDenied(DomainError):
    """The user's role does not allow the operation."""


class AuthenticationError(DomainError):
    """Credentials or token are missing or invalid."""


class PasswordChangeRequired(DomainError):
    """The user must change the password before getting tokens."""


class ChecksumMismatch(DomainError):
    """The content does not match its declared SHA-256."""
