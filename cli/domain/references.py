"""Template references ``host:port/organization/repo[:tag]`` (C-16, C-42).

A reference that starts with ``host:port`` is complete. Any other reference
is short and is completed from the left with the default prefix set with
``easyk8s work set``. The default tag is ``latest``.
"""
import re

from cli.data.models import Prefix, Reference
from cli.domain.errors import ValidationError


DEFAULT_TAG = "latest"

_REGISTRY = re.compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*):(\d{1,5})$"
)
# Same rules as the API: lowercase components and Docker-like tags.
_COMPONENT = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def parse_registry(text: str) -> str:
    """Validate a registry address.

    Args:
        text: ``host:port``.

    Returns:
        The same address.

    Raises:
        ValidationError: If it is not ``host:port`` with a valid port.
    """
    _split_registry(text)
    return text


def parse_prefix(text: str) -> Prefix:
    """Parse a default prefix.

    Args:
        text: ``host:port``, ``host:port/org`` or ``host:port/org/repo``.

    Returns:
        The prefix.

    Raises:
        ValidationError: If the prefix is not valid.
    """
    parts = text.split("/")
    if len(parts) > 3 or ":" in "/".join(parts[1:]):
        raise ValidationError(
            f"Invalid prefix '{text}', expected host:port[/org[/repo]]"
        )
    host, port = _split_registry(parts[0])
    names = parts[1:]
    for name in names:
        _check_component(name, text)
    return Prefix(host, port, *names)


def format_prefix(prefix: Prefix) -> str:
    """Write a prefix as text.

    Args:
        prefix: Prefix to write.

    Returns:
        ``host:port[/org[/repo]]``.
    """
    names = [n for n in (prefix.organization, prefix.repository) if n]
    return "/".join([f"{prefix.host}:{prefix.port}", *names])


def is_complete(text: str) -> bool:
    """Check whether a reference starts with ``host:port``.

    Args:
        text: Reference as written by the user.

    Returns:
        True if it does not need the prefix.
    """
    return bool(_REGISTRY.match(text.split("/", 1)[0]))


def parse(text: str, prefix: Prefix | None = None) -> Reference:
    """Parse a complete or short reference.

    Args:
        text: Reference as written by the user.
        prefix: Default prefix, or None if none was set.

    Returns:
        The complete reference.

    Raises:
        ValidationError: If the reference is invalid, or is short and the
            prefix is missing or does not have enough parts.
    """
    if is_complete(text):
        registry, _, path = text.partition("/")
        host, port = _split_registry(registry)
        names, tag = _split_tag(path, text)
        if len(names) != 2:
            raise ValidationError(
                f"Invalid reference '{text}', expected "
                "host:port/organization/repo[:tag]"
            )
        return Reference(host, port, names[0], names[1], tag)

    if prefix is None:
        raise ValidationError(
            f"'{text}' is a short reference; set a default prefix with "
            "'easyk8s work set host:port[/org[/repo]]' or write "
            "host:port/organization/repo[:tag]"
        )
    names, tag = _split_tag(text, text)
    defaults = [prefix.organization, prefix.repository]
    missing = 2 - len(names)
    if missing < 0 or any(name is None for name in defaults[:missing]):
        raise ValidationError(
            f"The prefix '{format_prefix(prefix)}' cannot complete '{text}'"
        )
    organization, repository = defaults[:missing] + names
    return Reference(prefix.host, prefix.port, organization, repository, tag)


def _split_registry(text: str) -> tuple[str, int]:
    """Split ``host:port``.

    Args:
        text: Address to split.

    Returns:
        The host and the port.

    Raises:
        ValidationError: If the address or the port are invalid.
    """
    match = _REGISTRY.match(text)
    if not match or not 0 < int(match.group(2)) < 65536:
        raise ValidationError(f"Invalid registry '{text}', expected host:port")
    return match.group(1), int(match.group(2))


def _split_tag(path: str, text: str) -> tuple[list[str], str]:
    """Split ``org/repo:tag`` (or a part of it) into names and tag.

    Args:
        path: Text after the registry, or the whole short reference.
        text: Whole reference, used in the error messages.

    Returns:
        The repository names (possibly empty) and the tag.

    Raises:
        ValidationError: If a name or the tag are invalid.
    """
    name_part, colon, tag = path.rpartition(":")
    if not colon:
        name_part, tag = path, DEFAULT_TAG
    if not _TAG.match(tag) or _SHA256.match(tag):
        raise ValidationError(f"Invalid tag in '{text}'")
    names = name_part.split("/") if name_part else []
    for name in names:
        _check_component(name, text)
    return names, tag


def _check_component(name: str, text: str) -> None:
    """Validate an organization or repository name.

    Args:
        name: Name to validate.
        text: Whole reference, used in the error message.

    Raises:
        ValidationError: If the name is not lowercase letters and digits,
            optionally joined by ``.``, ``_`` or ``-``.
    """
    if not _COMPONENT.match(name):
        raise ValidationError(
            f"Invalid name '{name}' in '{text}': use lowercase letters, "
            "digits, '.', '_' or '-'"
        )
