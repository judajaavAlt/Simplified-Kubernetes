"""Checking the YAML files of a template before storing or writing it."""
from collections.abc import Iterable

from cli.data.models import ArchiveEntry
from cli.domain import variables, yaml_files
from cli.domain.errors import ValidationError
from cli.persistence.document_codec import DocumentCodec


def check_yaml_files(codec: DocumentCodec, entries: Iterable[ArchiveEntry]) -> None:
    """Ensure every YAML file is well formed, reporting all problems together.

    Args:
        codec: YAML codec.
        entries: Files whose placeholders were already replaced.

    Raises:
        ValidationError: With one ``<path>: line N: …`` message per problem.
    """
    errors = []
    for entry in entries:
        if entry.content is None or not variables.is_text(entry.content):
            continue
        if not yaml_files.should_check(entry.path, entry.content.decode("utf-8")):
            continue
        errors.extend(f"{entry.path}: {p}" for p in codec.problems(entry.content))
    if errors:
        raise ValidationError(errors)
