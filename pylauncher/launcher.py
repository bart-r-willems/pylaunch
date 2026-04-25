"""Launch a process and detach so the launcher can exit immediately."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def launch(argv: list[str], cwd: str | Path) -> None:
    """Start argv with the given working directory, fully detached.

    The child process keeps running after the launcher exits.
    """
    cwd_str = str(cwd)
    kwargs: dict = {"cwd": cwd_str, "close_fds": True}

    if sys.platform == "win32":
        # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NEW_CONSOLE = 0x00000010

        # For interactive REPLs/Jupyter we want a fresh console window so the
        # user can actually see and type into it.
        kwargs["creationflags"] = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
    else:
        # Detach from the launcher's session so closing the launcher doesn't
        # kill the child.
        kwargs["start_new_session"] = True

    subprocess.Popen(argv, **kwargs)
