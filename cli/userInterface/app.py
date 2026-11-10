import traceback
from collections.abc import Callable

import click

from cli.domain.errors import CliError
from cli.presentation.auth_commands import login, logout
from cli.presentation.context import AppContext
from cli.presentation.instance_command import instance
from cli.presentation.services import CliServices
from cli.presentation.template_commands import template
from cli.presentation.work_commands import work


def build_cli() -> click.Group:
    """Assemble the root ``easyk8s`` command.

    Returns:
        The click group with every command.
    """

    @click.group()
    @click.option("--verbose", is_flag=True, help="Show full error traces.")
    @click.pass_obj
    def easyk8s(app: AppContext, verbose):
        """easyK8s: create, share and instantiate microservice templates.
        \f
        Args:
            app: Shared context.
            verbose: Show full error traces.
        """
        app.verbose = verbose

    for command in (template, work, login, logout, instance):
        easyk8s.add_command(command)
    return easyk8s


def run(argv: list[str] | None, factory: Callable[[], CliServices]) -> int:
    """Run a command and turn errors into messages and exit codes (C-39).

    Exit codes: 0 success, 1 usage or validation error, 2 registry or
    network error, 3 failed build or deploy command. Errors are printed as
    ``Error: <message>``; ``--verbose`` adds the traceback.

    Args:
        argv: Arguments without the program name; None reads ``sys.argv``.
        factory: Builds the use cases on first use.

    Returns:
        The exit code.
    """
    app = AppContext(factory)
    try:
        result = build_cli().main(args=argv, prog_name="easyk8s",
                                  standalone_mode=False, obj=app)
        return result if isinstance(result, int) else 0
    except CliError as error:
        _report(f"Error: {error}", app)
        return error.exit_code
    except click.exceptions.Abort:
        click.echo("Aborted", err=True)
        return 1
    except click.ClickException as error:
        error.show()
        return 1
    except Exception as error:  # Unexpected: still no trace unless --verbose.
        _report(f"Error: {error}", app)
        return 1


def _report(message: str, app: AppContext) -> None:
    """Print an error, with its traceback in verbose mode.

    Args:
        message: Error message.
        app: Shared context.
    """
    if app.verbose:
        click.echo(traceback.format_exc(), err=True, nl=False)
    click.echo(message, err=True)
