"""Discover environments and available apps.

Speed matters: we never *import* any package — we just check for the existence
of executables in each env's Scripts/ (Windows) or bin/ (Unix) directory.
"""
from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass


IS_WINDOWS = sys.platform == "win32"
EXE_SUFFIX = ".exe" if IS_WINDOWS else ""
BIN_DIR = "Scripts" if IS_WINDOWS else "bin"


# Apps the launcher knows about. Each entry maps a display name to the
# executable filename (without .exe — we add that on Windows). The "python"
# entry is special-cased: it always exists if the env exists.
KNOWN_APPS: dict[str, str] = {
    "Python (REPL)": "python",
    "IDLE": "idle",
    "Jupyter Lab": "jupyter-lab",
    "Jupyter Notebook": "jupyter-notebook",
    "Qt Console": "jupyter-qtconsole",
    "Marimo": "marimo",
    "IPython": "ipython",
    # Special: not a Python package, just a shell with the env on PATH.
    # Windows only; filtered out elsewhere on other platforms.
    "Command Prompt": "__cmd__",
}


@dataclass
class Environment:
    """A discovered Python environment."""
    name: str           # folder name, used for display
    path: Path          # root of the env (the dir containing Scripts/ or bin/)
    python_exe: Path    # path to python executable

    @property
    def bin_dir(self) -> Path:
        return self.path / BIN_DIR


def _find_python_in(env_path: Path) -> Path | None:
    """Return the python executable inside env_path, or None if not an env."""
    candidate = env_path / BIN_DIR / f"python{EXE_SUFFIX}"
    if candidate.is_file():
        return candidate
    # On some Linux setups python is symlinked as python3 only.
    if not IS_WINDOWS:
        alt = env_path / BIN_DIR / "python3"
        if alt.is_file():
            return alt
    return None


def discover_environments(env_root: str | Path) -> list[Environment]:
    """Find all virtual environments under env_root.

    A directory is considered an environment if it contains a python executable
    in the standard location. Returns environments sorted by name.
    """
    if not env_root:
        return []
    root = Path(env_root)
    if not root.is_dir():
        return []

    envs: list[Environment] = []
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            py = _find_python_in(child)
            if py is not None:
                envs.append(Environment(name=child.name, path=child, python_exe=py))
    except OSError:
        # Permissions or transient FS error — return whatever we got.
        pass

    envs.sort(key=lambda e: e.name.lower())
    return envs


def available_apps(env: Environment) -> list[str]:
    """Return the display names of apps available in this env, in known order.

    Python and IDLE ship with every standard install, so they're always listed
    if the env has a python executable. Everything else is checked by looking
    for the script in the env's bin directory.
    """
    found: list[str] = []
    for display_name, exe_base in KNOWN_APPS.items():
        if exe_base == "python":
            # Always available — that's why it's an env.
            found.append(display_name)
            continue
        if exe_base == "idle":
            # IDLE ships with CPython; it's a module, so check via -m later.
            # Just trust it exists if python does.
            found.append(display_name)
            continue
        if exe_base == "__cmd__":
            # cmd.exe ships with Windows; not a thing on Unix.
            if IS_WINDOWS:
                found.append(display_name)
            continue
        candidate = env.bin_dir / f"{exe_base}{EXE_SUFFIX}"
        # On Windows, console scripts may also exist as .exe; check both.
        if candidate.is_file():
            found.append(display_name)
    return found


def app_command(env: Environment, app_display_name: str) -> list[str]:
    """Build the command line to launch the given app in the given env.

    Returns the argv list ready for subprocess.Popen.
    """
    py = str(env.python_exe)
    if app_display_name == "Python (REPL)":
        return [py]
    if app_display_name == "IDLE":
        # IDLE as a module is the most reliable way across platforms.
        return [py, "-m", "idlelib"]
    if app_display_name == "Command Prompt":
        # Just launch cmd. The launcher prepends the env's Scripts dir to
        # PATH and sets VIRTUAL_ENV, so `python`, `pip`, etc. resolve to
        # the env without the user having to call activate.bat.
        import os
        return [os.environ.get("COMSPEC", "cmd.exe")]
    # For installed scripts, prefer running the executable directly so that
    # the env's own python is used and the script's shebang/launcher works.
    exe_base = KNOWN_APPS[app_display_name]
    exe_path = env.bin_dir / f"{exe_base}{EXE_SUFFIX}"
    if exe_path.is_file():
        return [str(exe_path)]
    # Fallback: run as module via the env's python.
    module_map = {
        "Jupyter Lab": "jupyterlab",
        "Jupyter Notebook": "notebook",
        "Qt Console": "qtconsole",
        "Marimo": "marimo",
        "IPython": "IPython",
    }
    module = module_map.get(app_display_name, exe_base)
    return [py, "-m", module]


def has_pip_audit(env: Environment) -> bool:
    """Return True if pip-audit appears to be installed in this env."""
    return (env.bin_dir / f"pip-audit{EXE_SUFFIX}").is_file()
