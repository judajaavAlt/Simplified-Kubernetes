"""Variable placeholders ``[%name%]`` (C-05, C-06, C-41).

Spaces inside the delimiter are optional, undeclared placeholders are left
untouched (so Helm and Go templates survive) and ``\\[%name%]`` is written
as the literal ``[%name%]``.
"""
import re
from collections.abc import Iterable, Mapping


_PLACEHOLDER = re.compile(r"(\\?)\[%\s*([A-Za-z_][A-Za-z0-9_]*)\s*%\]")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_valid_name(name) -> bool:
    """Check whether a variable name can be used in a placeholder.

    Args:
        name: Candidate name.

    Returns:
        True for a letter or ``_`` followed by letters, digits or ``_``.
    """
    return isinstance(name, str) and bool(_NAME.match(name))


def substitute(text: str, values: Mapping[str, str]) -> str:
    """Replace the declared placeholders of a text.

    Args:
        text: Text with placeholders.
        values: Value of each declared variable, already as text.

    Returns:
        The text with declared placeholders replaced, escaped ones turned
        into literals and the rest untouched.
    """
    def replace(match: re.Match) -> str:
        """Return the replacement of one placeholder.

        Args:
            match: Placeholder found.

        Returns:
            The literal, the value or the original text.
        """
        escaped, name = match.group(1), match.group(2)
        if escaped:
            return match.group(0)[1:]
        if name in values:
            return values[name]
        return match.group(0)

    return _PLACEHOLDER.sub(replace, text)


def uses(text: str, declared: Iterable[str]) -> tuple[str, ...]:
    """List the declared variables a text uses.

    Args:
        text: Text with placeholders.
        declared: Names of the declared variables.

    Returns:
        The names used, sorted and without repetitions.
    """
    names = set(declared)
    return tuple(sorted({
        match.group(2)
        for match in _PLACEHOLDER.finditer(text)
        if not match.group(1) and match.group(2) in names
    }))


def has_escape(text: str) -> bool:
    """Check whether a text has an escaped placeholder.

    Args:
        text: Text to check.

    Returns:
        True if it contains ``\\[%name%]``.
    """
    return any(match.group(1) for match in _PLACEHOLDER.finditer(text))


def needs_processing(text: str, declared: Iterable[str]) -> bool:
    """Check whether a text changes when the template is set up.

    Args:
        text: Text to check.
        declared: Names of the declared variables.

    Returns:
        True if it uses a declared variable or has an escape.
    """
    return bool(uses(text, declared)) or has_escape(text)


def is_text(content: bytes) -> bool:
    """Decide whether file content is text that may hold placeholders.

    Args:
        content: File bytes.

    Returns:
        True for UTF-8 content without NUL bytes.
    """
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
