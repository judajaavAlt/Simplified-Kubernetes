"""Exclusion rules with the ``.gitignore`` syntax (C-13).

Paths are relative to the folder of the ignore file and use ``/``.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """One line of an ignore file.

    Attributes:
        pattern: Compiled regular expression.
        include: True for ``!`` rules, which include the path again.
        directory_only: True if the rule ends with ``/``.
    """

    pattern: re.Pattern
    include: bool
    directory_only: bool


def to_regex(rule: str) -> str:
    """Translate a rule into a regular expression.

    Supports ``*``, ``**``, ``?``, anchoring (a ``/`` at the start or in the
    middle) and a trailing ``/`` for folders.

    Args:
        rule: Rule without the ``!`` prefix.

    Returns:
        The regular expression.
    """
    body = rule.rstrip("/")
    anchored = body.startswith("/") or "/" in body.strip("/")
    body = body.lstrip("/")
    regex, i = "", 0
    while i < len(body):
        if body.startswith("**/", i):
            regex, i = regex + "(?:.*/)?", i + 3
        elif body.startswith("**", i):
            regex, i = regex + ".*", i + 2
        elif body[i] == "*":
            regex, i = regex + "[^/]*", i + 1
        elif body[i] == "?":
            regex, i = regex + "[^/]", i + 1
        else:
            regex, i = regex + re.escape(body[i]), i + 1
    return ("^" if anchored else "(?:^|/)") + regex + "$"


def parse(text: str) -> list[Rule]:
    """Read the rules of an ignore file.

    Args:
        text: Content of the file.

    Returns:
        The rules in file order; empty lines and ``#`` comments are skipped.
    """
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        include = line.startswith("!")
        line = line[1:] if include else line
        rules.append(Rule(re.compile(to_regex(line)), include, line.endswith("/")))
    return rules


def is_excluded(path: str, is_dir: bool, rules: list[Rule]) -> bool:
    """Decide whether a path is excluded; the last matching rule wins.

    Args:
        path: Path relative to the ignore file, with ``/`` separators.
        is_dir: True if the path is a folder.
        rules: Rules from :func:`parse`.

    Returns:
        True if the path must be left out of the template.
    """
    excluded = False
    for rule in rules:
        if rule.directory_only and not is_dir:
            continue
        if rule.pattern.search(path):
            excluded = not rule.include
    return excluded
