import click

from cli.presentation.context import services


@click.group()
def work():
    """Default prefix for short references."""


@work.command(name="set")
@click.argument("prefix")
def set_command(prefix):
    """Set PREFIX: host:port, host:port/org or host:port/org/repo.
    \f
    Args:
        prefix: Default prefix.
    """
    click.echo(f"Default prefix: {services().set_prefix.execute(prefix)}")


@work.command()
def show():
    """Show the default prefix."""
    prefix = services().show_prefix.execute()
    click.echo(prefix or "No default prefix; set one with 'easyk8s work set'.")


@work.command()
def clear():
    """Remove the default prefix."""
    services().set_prefix.execute(None)
    click.echo("Default prefix removed")
