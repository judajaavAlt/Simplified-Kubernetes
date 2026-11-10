"""``KEY = VALUE`` files used for values, build and deploy (C-21)."""
from collections.abc import Iterable

from cli.data.models import Variable, VariableType
from cli.domain.errors import ValidationError
from cli.domain.values import format_value


def parse(text: str) -> dict[str, str]:
    """Read the values of a ``.env`` file.

    Empty lines and ``#`` comments are skipped, spaces around names and
    values are removed, and matching quotes around a value are removed.

    Args:
        text: Content of the file.

    Returns:
        The values by name, as text.

    Raises:
        ValidationError: With every line that has no ``=`` or no name.
    """
    result, errors = {}, []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"Line {number}: expected NAME = VALUE")
            continue
        name, value = (part.strip() for part in line.split("=", 1))
        if not name:
            errors.append(f"Line {number}: missing variable name")
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        result[name] = value
    if errors:
        raise ValidationError(errors)
    return result


def render(variables: Iterable[Variable]) -> str:
    """Write a sample ``.env`` file with the defaults.

    Each variable is preceded by its description as a comment; strings are
    quoted.

    Args:
        variables: Variables to write.

    Returns:
        Content of the file.
    """
    blocks = []
    for variable in variables:
        lines = [f"# {variable.description}"] if variable.description else []
        value = format_value(variable.default, variable.type)
        if variable.type is VariableType.STR:
            value = f'"{value}"'
        lines.append(f"{variable.name} = {value}")
        blocks.append("\n".join(lines) + "\n")
    return "\n".join(blocks)
