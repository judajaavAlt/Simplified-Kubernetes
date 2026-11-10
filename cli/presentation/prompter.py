import click

from cli.domain.ports import Prompter


class ClickPrompter(Prompter):
    """Asks the user in the terminal."""

    def choose_conflict_action(self, paths: list[str]) -> str:
        """Show the existing files once and ask what to do (C-43).

        Args:
            paths: Files that would be overwritten.

        Returns:
            ``all``, ``one`` or ``cancel``.
        """
        click.echo(f"{len(paths)} file(s) already exist:")
        for path in paths:
            click.echo(f"  {path}")
        answer = click.prompt(
            "[a] overwrite all / [o] one by one / [c] cancel",
            type=click.Choice(["a", "o", "c"]), default="c",
        )
        return {"a": "all", "o": "one", "c": "cancel"}[answer]

    def confirm_overwrite(self, path: str) -> bool:
        """Ask whether to overwrite one file.

        Args:
            path: File that already exists.

        Returns:
            True to overwrite it.
        """
        return click.confirm(f"Overwrite {path}?", default=False)

    def ask_new_password(self) -> str:
        """Ask a new password, twice.

        Returns:
            The new password.
        """
        click.echo("The registry requires a new password.")
        return click.prompt("New password", hide_input=True,
                            confirmation_prompt=True)
