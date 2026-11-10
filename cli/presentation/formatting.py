"""Text output of the commands."""
from datetime import datetime

from cli.data.models import Manifest, ManifestRecord, Stage, Variable
from cli.domain import ids, values
from cli.domain.commands import CommandView


def format_size(size: int) -> str:
    """Write a size like Docker (powers of 1000).

    Args:
        size: Size in bytes.

    Returns:
        For example ``512B``, ``1.5kB`` or ``12MB``.
    """
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.3g}{unit}"
        size /= 1000
    return f"{size}GB"


def format_moment(moment: datetime) -> str:
    """Write a moment in local time.

    Args:
        moment: Moment to write.

    Returns:
        ``YYYY-MM-DD HH:MM``.
    """
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Align rows in columns separated by two spaces.

    Args:
        headers: Column titles.
        rows: Cells of each row.

    Returns:
        The lines of the table.
    """
    widths = [max(len(str(c)) for c in column) for column in zip(headers, *rows)]
    return [
        "  ".join(str(c).ljust(w) for c, w in zip(row, widths)).rstrip()
        for row in [headers, *rows]
    ]


def template_rows(records: list[ManifestRecord]) -> list[list[str]]:
    """Turn index records into ``template list`` rows (C-19).

    A template with several tags gets one row per tag; an orphan shows
    ``<none>`` (C-18).

    Args:
        records: Local templates.

    Returns:
        Rows with repository, tag, short ID, creation and size.
    """
    rows = []
    for record in records:
        common = [ids.short(record.id), format_moment(record.created_at),
                  format_size(record.size)]
        if not record.tags:
            rows.append(["<none>", "<none>", *common])
        for tag in record.tags:
            rows.append([f"{tag.registry}/{tag.repository_path}", tag.tag, *common])
    return rows


def _variables(variables: tuple[Variable, ...]) -> list[str]:
    """Write a variable table.

    Args:
        variables: Variables to write.

    Returns:
        The lines, or a single line when there are none.
    """
    if not variables:
        return ["  (none)"]
    rows = [[v.name, v.type.value, values.format_value(v.default, v.type),
             v.description] for v in variables]
    return ["  " + line for line in table(["NAME", "TYPE", "DEFAULT", "DESCRIPTION"], rows)]


def _stage(title: str, stage: Stage) -> list[str]:
    """Write the variables and commands of a stage.

    Args:
        title: ``Build`` or ``Deploy``.
        stage: Stage to write.

    Returns:
        The lines.
    """
    commands = [f"  {n}. {c}" for n, c in enumerate(stage.commands, 1)] or ["  (none)"]
    return [f"{title} variables:", *_variables(stage.variables),
            f"{title} commands:", *commands]


def manifest_lines(manifest_id: str, manifest: Manifest) -> list[str]:
    """Write the documentation of a template (``template inspect``).

    Args:
        manifest_id: SHA-256 of the manifest.
        manifest: Manifest to describe.

    Returns:
        The lines.
    """
    lines = [
        f"ID:          {manifest_id}",
        f"Reference:   {manifest.reference}",
        f"Description: {manifest.description or '(none)'}",
        f"Layers:      {len(manifest.layers)}",
        "Variables (template setup):",
        *_variables(manifest.instantiation),
        *_stage("Build", manifest.build),
        *_stage("Deploy", manifest.deploy),
    ]
    if manifest.readme:
        lines += ["README:", *("  " + line for line in manifest.readme.splitlines())]
    return lines


def plan_lines(plan: list[tuple[str, list[CommandView]]]) -> list[str]:
    """Write the commands of a dry run.

    Args:
        plan: Resolved commands of each stage.

    Returns:
        The lines; standard commands show their native equivalent and
        destructive commands are marked.
    """
    lines = ["DRY RUN: nothing was executed."]
    for stage, views in plan:
        lines += ["", f"[{stage.upper()}]"]
        if not views:
            lines.append("  (no commands)")
        for number, view in enumerate(views, 1):
            mark = "   [DESTRUCTIVE]" if view.destructive else ""
            lines.append(f"  {number}. {view.text}{mark}")
            if view.native:
                lines.append(f"     -> {view.native}")
    return lines
