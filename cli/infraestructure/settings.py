import os
import platform
from collections.abc import Mapping
from pathlib import Path


def default_data_dir(
    env: Mapping[str, str] | None = None, system: str | None = None
) -> Path:
    """Return the folder of the CLI data (C-48).

    ``EASYK8S_DATA`` overrides it. Otherwise it is
    ``%LOCALAPPDATA%/judajaav/easyK8s`` on Windows and
    ``$XDG_DATA_HOME/easyk8s`` (by default ``~/.local/share/easyk8s``) on
    Linux and other systems.

    Args:
        env: Environment variables; None reads ``os.environ``.
        system: ``platform.system()`` value; None detects it.

    Returns:
        The data folder.
    """
    env = os.environ if env is None else env
    system = system or platform.system()
    if env.get("EASYK8S_DATA"):
        return Path(env["EASYK8S_DATA"])
    if system == "Windows":
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "judajaav" / "easyK8s"
    if env.get("XDG_DATA_HOME"):
        return Path(env["XDG_DATA_HOME"]) / "easyk8s"
    home = env.get("HOME") or str(Path.home())
    return Path(home) / ".local" / "share" / "easyk8s"
