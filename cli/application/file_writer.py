"""Writing generated files without overwriting by surprise (C-22, C-43)."""
from dataclasses import dataclass, field
from pathlib import Path

from cli.data.models import ArchiveEntry
from cli.domain.errors import CancelledError
from cli.domain.ports import Prompter
from cli.persistence.file_system import FileSystem


@dataclass(frozen=True)
class WriteResult:
    """Files written into the output folder.

    Attributes:
        written: Files written, relative to the output folder.
        skipped: Existing files the user chose to keep.
    """

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def write_files(
    fs: FileSystem,
    prompter: Prompter,
    output: Path,
    entries: list[ArchiveEntry],
    force: bool,
) -> WriteResult:
    """Write files and folders, asking before overwriting existing files.

    The list of existing files is shown once and the user chooses to
    overwrite all of them, decide one by one or cancel. Nothing is written
    before that answer.

    Args:
        fs: User files.
        prompter: Asks the user.
        output: Destination folder.
        entries: Paths relative to ``output``; None content means a folder.
        force: Overwrite without asking.

    Returns:
        The written and skipped files.

    Raises:
        CancelledError: If the user cancels.
    """
    conflicts = [
        e.path for e in entries
        if e.content is not None and fs.exists(output / e.path)
    ]
    skipped = []
    if conflicts and not force:
        action = prompter.choose_conflict_action(conflicts)
        if action == "cancel":
            raise CancelledError("Cancelled; nothing was written")
        if action == "one":
            skipped = [p for p in conflicts if not prompter.confirm_overwrite(p)]
    fs.make_dirs(output)
    written = []
    for entry in entries:
        if entry.content is None:
            fs.make_dirs(output / entry.path)
        elif entry.path not in skipped:
            fs.write_bytes(output / entry.path, entry.content)
            written.append(entry.path)
    return WriteResult(written, skipped)
