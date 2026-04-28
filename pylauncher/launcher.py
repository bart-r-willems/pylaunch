"""Launch a process and detach so the launcher can exit immediately."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


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
    cwd_str = str(cwd)
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
