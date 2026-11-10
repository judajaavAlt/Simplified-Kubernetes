"""easyK8s command line: create, share and instantiate microservice templates."""


def main(argv: list[str] | None = None) -> int:
    """Run the command line.

    The application is imported here so that importing the package has no
    side effects (no data folder is created).

    Args:
        argv: Arguments without the program name; None reads ``sys.argv``.

    Returns:
        The exit code.
    """
    from cli.app import main as run

    return run(argv)
