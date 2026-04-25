# pylauncher

A small, snappy desktop launcher for Python. Pick an environment, a working
directory, and an app (Python REPL, IDLE, Jupyter Lab/Notebook, Marimo, IPython),
then hit Launch.

- **Zero dependencies.** Pure stdlib + Tkinter (which ships with CPython on Windows).
- **Fast.** No package imports during discovery — it just looks for executables
  on disk. Settings are a single small JSON file.
- **Self-discovering.** Point it at the directory containing your virtual
  environments. It finds the envs, and per-env it finds which apps are installed.
  Apps that aren't installed in a given env aren't listed for that env.

## Run it

```
python pylauncher.py
```

or

```
python -m pylauncher
```

On first run it asks for the root directory containing your virtual
environments (e.g. `C:\envs\` or `~/venvs/`). Any subdirectory of that root
that has a `Scripts/python.exe` (Windows) or `bin/python` (Unix) is treated
as an environment.

## Directory list

The middle panel is your bookmarked working directories. Each one has an
**alias** (display name) and a **path**. Sortable by alias or by use count
(most-used first), toggleable from the bottom bar. Hit **Edit Directories…**
to add, edit, remove, or reset use counts.

Every successful launch bumps the use count for the chosen directory, so the
"sort by uses" option puts your favourites at the top automatically.

## Apps

The launcher detects these per environment:

| App              | Detection                                      |
| ---------------- | ---------------------------------------------- |
| Python (REPL)    | always (it's why an env is an env)             |
| IDLE             | always (ships with CPython, run as `-m idlelib`) |
| Jupyter Lab      | `jupyter-lab` in env's `Scripts/` or `bin/`    |
| Jupyter Notebook | `jupyter-notebook` in env's `Scripts/` or `bin/` |
| Marimo           | `marimo` in env's `Scripts/` or `bin/`         |
| IPython          | `ipython` in env's `Scripts/` or `bin/`        |

## Keyboard

- `Enter` — Launch
- `Escape` — Close the launcher
- Double-click any list item — Launch

## Files

Settings live at:

- Windows: `%APPDATA%\pylauncher\settings.json`
- macOS/Linux: `$XDG_CONFIG_HOME/pylauncher/settings.json` (default `~/.config/pylauncher/`)

Schema:

```json
{
  "env_root": "C:\\envs",
  "directories": [
    {"alias": "Desktop", "path": "C:\\Users\\Me\\Desktop", "uses": 12},
    {"alias": "Project X", "path": "D:\\code\\projx", "uses": 47}
  ],
  "sort_directories_by": "uses",
  "last_env": "data-env",
  "last_dir_alias": "Project X",
  "last_app": "Jupyter Lab"
}
```

## Project layout

```
pylauncher/
├── pylauncher.py        # convenience entry point
└── pylauncher/
    ├── __init__.py
    ├── __main__.py      # python -m pylauncher
    ├── settings.py      # JSON config load/save
    ├── discovery.py     # find envs + per-env apps
    ├── launcher.py      # detached subprocess launch
    └── ui.py            # Tkinter UI
```
