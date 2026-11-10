"""Entry point of the ``easyk8s`` executable."""
from cli.infraestructure.composition import build_services
from cli.userInterface.app import run


def main(argv: list[str] | None = None) -> int:
    """Run the command line with the real implementations.

    Args:
        argv: Arguments without the program name; None reads ``sys.argv``.

    Returns:
        The exit code.
    """
    return run(argv, build_services)
