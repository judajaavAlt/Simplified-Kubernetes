"""Typed values of the variables (C-08, C-09, C-51)."""
import re
from collections.abc import Iterable, Mapping

from cli.data.models import Variable, VariableType
from cli.domain.errors import ValidationError


_INT = re.compile(r"^[+-]?\d+$")
_FLOAT = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def convert(name: str, raw: str, vtype: VariableType):
    """Convert a value written as text (``.env`` files) to its type.

    Booleans only accept ``true`` and ``false`` in lowercase.

    Args:
        name: Variable name, used in the error message.
        raw: Value as text.
        vtype: Declared type.

    Returns:
        The typed value.

    Raises:
        ValidationError: If the text is not a value of that type.
    """
    vtype = VariableType(vtype)
    if vtype is VariableType.STR:
        return raw
    if vtype is VariableType.INT and _INT.match(raw):
        return int(raw)
    if vtype is VariableType.FLOAT and _FLOAT.match(raw):
        return float(raw)
    if vtype is VariableType.BOOL and raw in ("true", "false"):
        return raw == "true"
    raise ValidationError(
        f"Variable '{name}' expects {vtype.value}, got {raw!r}"
    )


def check_default(name: str, default, vtype: VariableType) -> list[str]:
    """Check that a default exists and matches its type.

    A float accepts whole numbers; no other type is converted.

    Args:
        name: Variable name, used in the messages.
        default: Default read from YAML; None when missing.
        vtype: Declared type.

    Returns:
        The problems found; empty if the default is valid.
    """
    if default is None:
        return [f"Variable '{name}' needs a default of type {vtype.value}"]
    valid = {
        VariableType.STR: isinstance(default, str),
        VariableType.INT: isinstance(default, int)
        and not isinstance(default, bool),
        VariableType.FLOAT: isinstance(default, (int, float))
        and not isinstance(default, bool),
        VariableType.BOOL: isinstance(default, bool),
    }[VariableType(vtype)]
    if valid:
        return []
    return [
        f"Default of variable '{name}' must be {vtype.value}, got {default!r}"
    ]


def format_value(value, vtype: VariableType) -> str:
    """Write a typed value as the text that replaces its placeholder.

    Args:
        value: Typed value.
        vtype: Declared type.

    Returns:
        ``true``/``false`` for booleans, ``str(value)`` otherwise.
    """
    if VariableType(vtype) is VariableType.BOOL:
        return "true" if value else "false"
    return str(value)


def resolve(
    declared: Iterable[Variable], overrides: Mapping[str, str]
) -> dict[str, object]:
    """Combine defaults with values written as text.

    Args:
        declared: Declared variables.
        overrides: Values from a ``.env`` file, by name.

    Returns:
        The typed value of every declared variable.

    Raises:
        ValidationError: With every unknown name and every invalid value.
    """
    declared = list(declared)
    known = {variable.name for variable in declared}
    errors = [
        f"Unknown variable '{name}'" for name in overrides if name not in known
    ]
    resolved = {}
    for variable in declared:
        if variable.name not in overrides:
            resolved[variable.name] = variable.default
            continue
        try:
            resolved[variable.name] = convert(
                variable.name, overrides[variable.name], variable.type
            )
        except ValidationError as error:
            errors.extend(error.errors)
    if errors:
        raise ValidationError(errors)
    return resolved
