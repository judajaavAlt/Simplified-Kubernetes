"""
Server command line.

    python -m api create-admin --nickname root   (first admin, run locally)
    python -m api serve --host 0.0.0.0 --port 8000
"""
import argparse
import getpass
import sys

from api.domain.errors import DomainError
from api.infraestructure.composition import bootstrap_admin, build_app
from api.infraestructure.settings import Settings


def main(argv: list[str] | None = None) -> int:
    """Run the server command line.

    Commands:

    * ``create-admin --nickname NAME [--password PASSWORD]``: create the
      first admin; the password is prompted when omitted.
    * ``serve [--host HOST] [--port PORT]``: run the HTTP API.

    Args:
        argv: Arguments without the program name; None reads ``sys.argv``.

    Returns:
        The exit code: 0 on success, 1 on a business rule violation.
    """
    parser = argparse.ArgumentParser(prog="python -m api")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="Run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    admin = commands.add_parser(
        "create-admin", help="Create the first admin user"
    )
    admin.add_argument("--nickname", required=True)
    admin.add_argument(
        "--password", help="Prompted when omitted (recommended)"
    )

    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.command == "create-admin":
        password = args.password or getpass.getpass("Admin password: ")

        try:
            user_id = bootstrap_admin(settings, args.nickname, password)
        except DomainError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1

        print(f"Admin '{args.nickname}' created with id {user_id}")
        return 0

    import uvicorn

    uvicorn.run(build_app(settings), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
