"""Launch a process and detach so the launcher can exit immediately."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


# Matches a Windows drive-letter-only path: "R:" or "R:\". Used to ensure we
# pass "R:\" (with trailing backslash) to subprocess and child apps — without
# it, Windows interprets "R:" as "current dir on drive R" rather than "root
# of drive R", and tools like Jupyter Lab fail with "directory not found".
_DRIVE_ROOT_RE = re.compile(r"^[A-Za-z]:[\\/]?$")


def _normalize_cwd(cwd: str | Path) -> str:
    """Return cwd as a string, fixing Windows drive-root paths.

    pathlib and os.path routinely strip trailing separators, turning "R:\\"
    into "R:". This re-adds the trailing backslash for drive-root paths on
    Windows so subprocess / spawned apps see a real directory.
    """
    s = str(cwd)
    if sys.platform == "win32" and _DRIVE_ROOT_RE.match(s):
        return s[:2] + "\\"
    return s


def launch(
    argv: list[str],
    cwd: str | Path,
    env_overrides: dict[str, str] | None = None,
    console_title: str | None = None,
) -> None:
    """Start argv with the given working directory, fully detached.

    The child process keeps running after the launcher exits.

    env_overrides, if given, is merged on top of the current process
    environment for the child only — used to "activate" a venv inside a
    Command Prompt by prepending Scripts to PATH and setting VIRTUAL_ENV.

    console_title, if given (Windows only), sets the title of the new
    console window via STARTUPINFO.lpTitle. Apps that explicitly retitle
    their own console (cmd.exe, IPython, Jupyter) will overwrite this
    after startup; for those we wrap the invocation with `cmd /k title …`.
    """
    cwd_str = _normalize_cwd(cwd)
    kwargs: dict = {"cwd": cwd_str, "close_fds": True}

    if env_overrides:
        child_env = os.environ.copy()
        child_env.update(env_overrides)
        kwargs["env"] = child_env

    if sys.platform == "win32":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NEW_CONSOLE = 0x00000010

        # For interactive REPLs/Jupyter we want a fresh console window so the
        # user can actually see and type into it.
        kwargs["creationflags"] = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP

        if console_title:
            # STARTUPINFO.lpTitle sets the new console window's title. This
            # is honoured by graphical-console apps but cmd/IPython/Jupyter
            # call SetConsoleTitle on startup and overwrite it. The caller
            # handles those by using a `cmd /k title ... & realcmd` wrapper.
            si = subprocess.STARTUPINFO()
            si.lpTitle = console_title
            kwargs["startupinfo"] = si
    else:
        # Detach from the launcher's session so closing the launcher doesn't
        # kill the child.
        kwargs["start_new_session"] = True

    subprocess.Popen(argv, **kwargs)
