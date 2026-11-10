import re

from api.domain.checksum import is_sha256_hex
from api.domain.errors import InvalidInput


# <organization>/<repo>[/<more>], lowercase like Docker.
_COMPONENT = r"[a-z0-9]+(?:[._-][a-z0-9]+)*"
_REPOSITORY = re.compile(rf"^{_COMPONENT}(?:/{_COMPONENT})+$")
_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_NICKNAME = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")

MIN_PASSWORD_LENGTH = 8


def validate_repository(name: str) -> None:
    """Validate a repository name such as ``org/repo``.

    Components are lowercase letters and digits, optionally joined by
    ``.``, ``_`` or ``-``, like Docker repository names.

    Args:
        name: Repository name to validate.

    Raises:
        InvalidInput: If the name does not follow ``<organization>/<repo>``.
    """
    if not _REPOSITORY.match(name):
        raise InvalidInput(
            f"Invalid repository '{name}', expected <organization>/<repo>"
        )


def validate_tag(tag: str) -> None:
    """Validate a tag name such as ``latest`` or ``v1.2``.

    Args:
        tag: Tag to validate.

    Raises:
        InvalidInput: If the tag has invalid characters, is longer than
            128 characters or looks like a SHA-256 signature.
    """
    if not _TAG.match(tag):
        raise InvalidInput(f"Invalid tag '{tag}'")

    if is_sha256_hex(tag):
        raise InvalidInput("A tag cannot look like a SHA-256 signature")


def validate_nickname(nickname: str) -> None:
    """Validate a user nickname.

    Args:
        nickname: Nickname to validate.

    Raises:
        InvalidInput: If it does not have 3 to 32 letters, digits,
            ``_``, ``.`` or ``-``.
    """
    if not _NICKNAME.match(nickname):
        raise InvalidInput(
            "Nickname must have 3 to 32 letters, digits, '_', '.' or '-'"
        )


def validate_password(password: str) -> None:
    """Validate the strength of a new password.

    Args:
        password: Password in plain text.

    Raises:
        InvalidInput: If it is shorter than ``MIN_PASSWORD_LENGTH``.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidInput(
            f"Password must have at least {MIN_PASSWORD_LENGTH} characters"
        )
