from collections.abc import Callable

import click

from cli.presentation.services import CliServices


class AppContext:
    """Object shared by every command through ``click.Context.obj``.

    The use cases are built on first use, so ``--help`` does not touch the
    data folder.

    Attributes:
        verbose: Show full tracebacks on errors.
    """

    def __init__(self, factory: Callable[[], CliServices]):
        """Create the context.

        Args:
            factory: Builds the use cases.
        """
        self._factory = factory
        self._services: CliServices | None = None
        self.verbose = False

    @property
    def services(self) -> CliServices:
        """The use cases, built on first access."""
        if self._services is None:
            self._services = self._factory()
        return self._services


def services() -> CliServices:
    """Return the use cases of the current command.

    Returns:
        The use cases.
    """
    return click.get_current_context().find_object(AppContext).services


def report(event: str) -> None:
    """Show a progress message.

    Args:
        event: Message to show.
    """
    click.echo(f"  {event}")
