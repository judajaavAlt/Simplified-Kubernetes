"""Build and deploy commands (C-34, C-44, C-45, C-46).

Each command is one line. If its first word is a standard command
(``makeDirectory``, ``removePath``…), the CLI runs it itself in the same way
on Windows and Linux. Otherwise the program is run directly, without a
shell, so pipes and redirections are not available.
"""
import re
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PureWindowsPath

from cli.data.models import Stage, Variable
from cli.domain import values, variables
from cli.domain.errors import ValidationError


# name -> (minimum arguments, maximum arguments or None)
STANDARD_COMMANDS = {
    "makeDirectory": (1, 1),
    "removePath": (1, 1),
    "copyPath": (2, 2),
    "movePath": (2, 2),
    "writeFile": (1, None),
    "changeDirectory": (1, 1),
    "setEnv": (2, 2),
    "print": (0, None),
}

_OPERATORS = ("&&", "||", "|", ">", "<", ";")
_CAMEL_CASE = re.compile(r"^[a-z]+[A-Z][A-Za-z]*$")


def tokenize(line: str) -> list[str]:
    """Split a command line into words.

    Words are separated by spaces; ``'…'`` and ``"…"`` group words and
    backslashes are kept as written, so Windows paths work.

    Args:
        line: Command line.

    Returns:
        The words, without quotes.

    Raises:
        ValidationError: If a quote is not closed or the line has an
            unquoted shell operator (``|``, ``>``, ``<``, ``&&``, ``||``,
            ``;``).
    """
    words, current, quote, started = [], [], None, False
    i = 0
    while i < len(line):
        char = line[i]
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "'\"":
            quote, started = char, True
        elif line.startswith("[%", i) and "%]" in line[i:]:
            # A placeholder may contain spaces: keep it in one word.
            end = line.index("%]", i) + 2
            current.append(line[i:end])
            started = True
            i = end
            continue
        elif char.isspace():
            if started:
                words.append("".join(current))
                current, started = [], False
        else:
            operator = next(
                (op for op in _OPERATORS if line.startswith(op, i)), None
            )
            if operator:
                raise ValidationError(
                    f"Shell operator '{operator}' is not supported in "
                    f"'{line}'; quote it or use a standard command"
                )
            current.append(char)
            started = True
        i += 1
    if quote:
        raise ValidationError(f"Unclosed quote in '{line}'")
    if started:
        words.append("".join(current))
    return words


def validate(line: str, names: Iterable[str]) -> list[str]:
    """Check a command line before it is stored or run.

    Args:
        line: Command line.
        names: Variables the command may use.

    Returns:
        The problems found; empty if the command is valid.
    """
    try:
        words = tokenize(line)
    except ValidationError as error:
        return error.errors
    if not words:
        return ["Empty command"]
    errors = []
    name = words[0]
    if name in STANDARD_COMMANDS:
        low, high = STANDARD_COMMANDS[name]
        count = len(words) - 1
        if count < low or (high is not None and count > high):
            expected = str(low) if low == high else f"at least {low}"
            errors.append(
                f"'{name}' expects {expected} argument(s) in '{line}'"
            )
    elif _CAMEL_CASE.match(name):
        errors.append(f"Unknown standard command '{name}' in '{line}'")
    known = set(names)
    for word in words:
        for used in variables.uses(word, _all_names(word)):
            if used not in known:
                errors.append(f"Unknown variable '{used}' in '{line}'")
    return errors


def _all_names(text: str) -> list[str]:
    """List every placeholder name of a text, declared or not.

    Args:
        text: Text with placeholders.

    Returns:
        The names found.
    """
    return re.findall(r"(?<!\\)\[%\s*([A-Za-z_][A-Za-z0-9_]*)\s*%\]", text)


def resolve_stage(
    stage: Stage, shared: Iterable[Variable], overrides: Mapping[str, str]
) -> list[list[str]]:
    """Resolve the commands of a stage into argument lists.

    Values are taken, from lowest to highest priority, from the stage
    defaults, the values chosen during the setup (``shared``) and the
    stage ``.env`` file. Placeholders are replaced word by word after the
    line is split, so a value with spaces stays one argument.

    Args:
        stage: Build or deploy stage.
        shared: Instantiation variables whose defaults are the chosen values.
        overrides: Values from the stage ``.env`` file, as text.

    Returns:
        One argument list per command.

    Raises:
        ValidationError: With every unknown name, invalid value or invalid
            command.
    """
    declared = {v.name: v for v in shared}
    for variable in stage.variables:
        declared.setdefault(variable.name, variable)
    resolved = values.resolve(declared.values(), overrides)
    text = {
        name: values.format_value(value, declared[name].type)
        for name, value in resolved.items()
    }
    errors, result = [], []
    for line in stage.commands:
        problems = validate(line, text)
        if problems:
            errors.extend(problems)
            continue
        result.append([variables.substitute(w, text) for w in tokenize(line)])
    if errors:
        raise ValidationError(errors)
    return result


@dataclass(frozen=True)
class CommandView:
    """How a resolved command is shown in a dry run.

    Attributes:
        text: The command as it will run.
        native: Equivalent command of the current system for a standard
            command, or None for an external program.
        destructive: True if the command may delete something.
    """

    text: str
    native: str | None
    destructive: bool


_DESTRUCTIVE_PROGRAMS = {"rm", "rmdir", "del", "erase", "rd", "remove-item"}
_DESTRUCTIVE_WORDS = {"delete", "uninstall", "rm", "rmi", "prune", "del",
                      "destroy"}
_TOOLS = {"kubectl", "helm", "docker", "podman", "terraform"}


def describe(argv: list[str], system: str) -> CommandView:
    """Describe a resolved command for the dry run.

    Args:
        argv: Resolved command.
        system: ``Windows`` or ``Linux`` (other systems use Linux syntax).

    Returns:
        The text, the native equivalent and whether it is destructive.
    """
    text = " ".join(_display(word) for word in argv)
    native = None
    if argv[0] in STANDARD_COMMANDS:
        native = (_windows if system == "Windows" else _linux)(argv)
    return CommandView(text, native, is_destructive(argv))


def is_destructive(argv: list[str]) -> bool:
    """Tell whether a command may delete resources or files.

    Args:
        argv: Resolved command.

    Returns:
        True for ``removePath``, deleting programs (``rm``, ``del``…) and
        delete-like subcommands of kubectl, helm, docker, podman and
        terraform.
    """
    if argv[0] in STANDARD_COMMANDS:
        return argv[0] == "removePath"
    program = PureWindowsPath(argv[0]).name.lower()
    program = program[:-4] if program.endswith(".exe") else program
    if program in _DESTRUCTIVE_PROGRAMS:
        return True
    return program in _TOOLS and any(
        word.lower() in _DESTRUCTIVE_WORDS for word in argv[1:4]
    )


def _display(word: str) -> str:
    """Quote a word for display if it is empty or has spaces.

    Args:
        word: Word to show.

    Returns:
        The word, between double quotes if needed.
    """
    return f'"{word}"' if not word or any(c.isspace() for c in word) else word


def _windows(argv: list[str]) -> str:
    """Write a standard command as its PowerShell equivalent.

    Args:
        argv: Standard command.

    Returns:
        The PowerShell command.
    """
    q = [_ps_quote(word) for word in argv[1:]]
    name = argv[0]
    if name == "makeDirectory":
        return f"New-Item -ItemType Directory -Force -Path {q[0]}"
    if name == "removePath":
        return f"Remove-Item -Recurse -Force -Path {q[0]}"
    if name == "copyPath":
        return f"Copy-Item -Recurse -Force -Path {q[0]} -Destination {q[1]}"
    if name == "movePath":
        return f"Move-Item -Force -Path {q[0]} -Destination {q[1]}"
    if name == "writeFile":
        return f"Set-Content -Path {q[0]} -Value {_ps_quote(' '.join(argv[2:]))}"
    if name == "changeDirectory":
        return f"Set-Location -Path {q[0]}"
    if name == "setEnv":
        return f"$env:{argv[1]} = {q[1]}"
    return f"Write-Output {_ps_quote(' '.join(argv[1:]))}"


def _linux(argv: list[str]) -> str:
    """Write a standard command as its POSIX shell equivalent.

    Args:
        argv: Standard command.

    Returns:
        The shell command.
    """
    q = [shlex.quote(word) for word in argv[1:]]
    name = argv[0]
    if name == "makeDirectory":
        return f"mkdir -p {q[0]}"
    if name == "removePath":
        return f"rm -rf {q[0]}"
    if name == "copyPath":
        return f"cp -r {q[0]} {q[1]}"
    if name == "movePath":
        return f"mv {q[0]} {q[1]}"
    if name == "writeFile":
        text = shlex.quote(" ".join(argv[2:]))
        return f"printf '%s\\n' {text} > {q[0]}"
    if name == "changeDirectory":
        return f"cd {q[0]}"
    if name == "setEnv":
        return f"export {argv[1]}={q[1]}"
    return f"echo {shlex.quote(' '.join(argv[1:]))}"


def _ps_quote(word: str) -> str:
    """Quote a word as a PowerShell literal string.

    Args:
        word: Word to quote.

    Returns:
        The word between single quotes.
    """
    return "'" + word.replace("'", "''") + "'"
