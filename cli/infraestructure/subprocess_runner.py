import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from cli.domain.errors import CliError, CommandFailedError
from cli.domain.ports import CommandRunner


def _is_root() -> bool:
    """Tell whether the process runs as root on a POSIX system.

    Returns:
        True for user ID 0.
    """
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _is_elevated() -> bool:
    """Tell whether the process runs as administrator on Windows.

    Returns:
        True for an elevated process.
    """
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


class SubprocessRunner(CommandRunner):
    """Runs programs directly, without a shell (C-34, C-35, C-46).

    Programs are found in ``PATH`` (on Windows also with the ``PATHEXT``
    extensions, so ``.exe``, ``.cmd`` and ``.bat`` work). Output is shown
    while the program runs. With ``--admin``, Linux uses ``sudo`` and
    Windows requires a terminal opened as administrator.
    """

    def __init__(
        self,
        system_name: str | None = None,
        is_root: Callable[[], bool] = _is_root,
        is_elevated: Callable[[], bool] = _is_elevated,
    ):
        """Create the runner.

        Args:
            system_name: ``platform.system()`` value; None detects it.
            is_root: Tells whether the process is root (POSIX).
            is_elevated: Tells whether the process is elevated (Windows).
        """
        self._system = system_name or platform.system()
        self._is_root = is_root
        self._is_elevated = is_elevated

    def system(self) -> str:
        """Name the operating system.

        Returns:
            The ``platform.system()`` value.
        """
        return self._system

    def environment(self) -> dict[str, str]:
        """Return a copy of the process environment.

        Returns:
            The environment variables.
        """
        return dict(os.environ)

    def check_admin(self) -> None:
        """Ensure programs can run with administrator rights.

        Raises:
            CliError: On Windows if the terminal is not elevated, or on
                Linux if the user is not root and ``sudo`` is missing.
        """
        if self._system == "Windows":
            if not self._is_elevated():
                raise CliError(
                    "--admin needs a terminal opened as administrator"
                )
        elif not self._is_root() and shutil.which("sudo") is None:
            raise CliError("--admin needs root or sudo")

    def run(self, argv, cwd: Path, env: dict[str, str], admin: bool) -> int:
        """Run a program and wait for it.

        Args:
            argv: Program and its arguments.
            cwd: Working directory.
            env: Environment variables.
            admin: Run with administrator rights.

        Returns:
            The exit code.

        Raises:
            CommandFailedError: If the program is not found.
        """
        search = env.get("PATH") or env.get("Path")
        program = shutil.which(argv[0], path=search)
        if program is None:
            raise CommandFailedError(f"Program not found: {argv[0]}")
        command = [program, *argv[1:]]
        if admin and self._system != "Windows" and not self._is_root():
            command = [shutil.which("sudo", path=search), *command]
        return subprocess.run(command, cwd=cwd, env=env).returncode
