from pathlib import Path

import click

from cli.domain import ids
from cli.presentation import formatting
from cli.presentation.context import report, services


@click.group()
def template():
    """Create, share and instantiate templates."""


@template.command()
@click.option("-c", "--config", "config", default="template.yaml",
              show_default=True, type=click.Path(path_type=Path),
              help="Path of template.yaml.")
@click.option("-e", "--exclude", type=click.Path(path_type=Path),
              help="Ignore file (default: .templateignore, else .gitignore).")
def create(config, exclude):
    """Create a template from a template.yaml.
    \f
    Args:
        config: Path of ``template.yaml``.
        exclude: Explicit ignore file, or None for the default.
    """
    result = services().create.execute(config, exclude)
    click.echo(f"Created {result.reference}")
    click.echo(f"ID: {result.manifest_id}")


@template.command(name="list")
def list_command():
    """List the local templates."""
    rows = formatting.template_rows(services().list.execute())
    if not rows:
        click.echo("No templates found.")
        return
    for line in formatting.table(["REPOSITORY", "TAG", "ID", "CREATED", "SIZE"], rows):
        click.echo(line)


@template.command()
@click.argument("name")
def inspect(name):
    """Show the documentation, variables and commands of NAME.
    \f
    Args:
        name: Reference, ID or ID prefix.
    """
    manifest_id, manifest = services().inspect.execute(name)
    for line in formatting.manifest_lines(manifest_id, manifest):
        click.echo(line)


@template.command()
@click.argument("name")
@click.option("-v", "--values", type=click.Path(path_type=Path),
              help="Values file (default: values.env if it exists).")
@click.option("-o", "--output", default=".", show_default=True,
              type=click.Path(path_type=Path, file_okay=False),
              help="Destination folder.")
@click.option("-s", "--sample", is_flag=True,
              help="Only write sample values.env, build.env and deploy.env.")
@click.option("-f", "--force", is_flag=True,
              help="Overwrite existing files without asking.")
def setup(name, values, output, sample, force):
    """Instantiate template NAME.
    \f
    Args:
        name: Reference, ID or ID prefix.
        values: Values file, or None for the default.
        output: Destination folder.
        sample: Only write the sample ``.env`` files.
        force: Overwrite existing files without asking.
    """
    if sample:
        result = services().samples.execute(name, output, force)
    else:
        result = services().setup.execute(name, output, values, force)
    click.echo(f"Wrote {len(result.written)} file(s) in {output}")
    for path in result.skipped:
        click.echo(f"Kept existing {path}")


@template.command()
@click.argument("source")
@click.argument("target")
def tag(source, target):
    """Create reference TARGET for template SOURCE.
    \f
    Args:
        source: Reference, ID or ID prefix.
        target: New reference.
    """
    click.echo(f"Tagged {services().tag.execute(source, target)}")


@template.command()
@click.argument("name")
@click.option("--remote", is_flag=True, help="Also delete it in the registry.")
def rm(name, remote):
    """Remove a reference, or a whole template by ID.
    \f
    Args:
        name: Reference, ID or ID prefix.
        remote: Also delete the manifest in the registry.
    """
    result = services().remove.execute(name, remote)
    for reference in result.untagged:
        click.echo(f"Untagged: {reference}")
    for blob_id in result.deleted:
        click.echo(f"Deleted: {ids.short(blob_id)}")


@template.command()
@click.argument("name")
def push(name):
    """Upload template NAME to its registry.
    \f
    Args:
        name: Reference of the template.
    """
    result = services().push.execute(name, report)
    click.echo(f"Pushed {result.reference} ({result.uploaded} uploaded, "
               f"{result.skipped} already in the registry)")


@template.command()
@click.argument("reference")
def pull(reference):
    """Download template REFERENCE from its registry.
    \f
    Args:
        reference: Reference of the template.
    """
    result = services().pull.execute(reference, report)
    click.echo(f"Pulled {result.reference} ({result.downloaded} downloaded)")
    click.echo(f"ID: {result.manifest_id}")


@template.command()
def reindex():
    """Rebuild the local index from the stored manifests."""
    count = services().reindex.execute()
    click.echo(f"Indexed {count} template(s)")
