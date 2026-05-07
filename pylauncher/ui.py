"""Tkinter UI for pylauncher.

Layout:
    [ Environments ] [ Directories ] [ Apps ]
    [ status / sort toggle / edit dirs / launch ]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path

from .settings import Settings, CONFIG_DIR
from .discovery import discover_environments, available_apps, app_command, has_pip_audit, Environment
from .launcher import launch


PADDING = 6


class DirectoryEditor(tk.Toplevel):
    """Modal-ish dialog for adding/removing/editing directory aliases."""

    def __init__(self, parent: "App", settings: Settings):
        super().__init__(parent)
        self.title("Edit Directories")
        self.settings = settings
        self.parent_app = parent
        self.transient(parent)
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Treeview with alias / path / uses columns.
        frame = ttk.Frame(self, padding=PADDING)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        cols = ("alias", "path", "uses")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        self.tree.heading("alias", text="Alias")
        self.tree.heading("path", text="Path")
        self.tree.heading("uses", text="Uses")
        self.tree.column("alias", width=120, anchor="w")
        self.tree.column("path", width=320, anchor="w")
        self.tree.column("uses", width=60, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        # Buttons.
        btns = ttk.Frame(self, padding=(PADDING, 0, PADDING, PADDING))
        btns.grid(row=1, column=0, sticky="ew")
        ttk.Button(btns, text="Add…", command=self._add).pack(side="left")
        ttk.Button(btns, text="Edit…", command=self._edit).pack(side="left", padx=(PADDING, 0))
        ttk.Button(btns, text="Remove", command=self._remove).pack(side="left", padx=(PADDING, 0))
        ttk.Button(btns, text="Reset uses", command=self._reset_uses).pack(side="left", padx=(PADDING, 0))
        ttk.Button(btns, text="Close", command=self._close).pack(side="right")

        self._refresh()

        # Center over parent.
        self.update_idletasks()
        x = parent.winfo_rootx() + 40
        y = parent.winfo_rooty() + 40
        self.geometry(f"+{x}+{y}")

    def _refresh(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for entry in self.settings.sorted_directories():
            self.tree.insert(
                "", "end",
                values=(entry["alias"], entry["path"], entry.get("uses", 0)),
            )

    def _selected_alias(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0], "values")[0]

    def _add(self) -> None:
        path = filedialog.askdirectory(parent=self, title="Pick a directory")
        if not path:
            return
        alias = simpledialog.askstring(
            "Alias",
            f"Alias for {path}:",
            parent=self,
            initialvalue=Path(path).name,
        )
        if not alias:
            return
        alias = alias.strip()
        if not alias:
            return
        if not self.settings.add_directory(alias, path):
            messagebox.showerror("Duplicate alias", f"Alias '{alias}' is already in use.", parent=self)
            return
        self.settings.save()
        self._refresh()

    def _edit(self) -> None:
        alias = self._selected_alias()
        if alias is None:
            return
        entry = next(
            (d for d in self.settings.data["directories"] if d["alias"] == alias),
            None,
        )
        if entry is None:
            return
        new_alias = simpledialog.askstring(
            "Edit alias", "Alias:", parent=self, initialvalue=entry["alias"]
        )
        if new_alias is None:
            return
        new_alias = new_alias.strip()
        if not new_alias:
            return
        new_path = filedialog.askdirectory(
            parent=self, title="Pick directory", initialdir=entry["path"]
        )
        if not new_path:
            new_path = entry["path"]
        if not self.settings.update_directory(alias, new_alias, new_path):
            messagebox.showerror("Duplicate alias", f"Alias '{new_alias}' is already in use.", parent=self)
            return
        self.settings.save()
        self._refresh()

    def _remove(self) -> None:
        alias = self._selected_alias()
        if alias is None:
            return
        if not messagebox.askyesno("Remove", f"Remove '{alias}'?", parent=self):
            return
        self.settings.remove_directory(alias)
        self.settings.save()
        self._refresh()

    def _reset_uses(self) -> None:
        if not messagebox.askyesno(
            "Reset uses", "Reset use counts for all directories?", parent=self
        ):
            return
        for entry in self.settings.data["directories"]:
            entry["uses"] = 0
        self.settings.save()
        self._refresh()

    def _close(self) -> None:
        self.parent_app.refresh_directories()
        self.destroy()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("pylauncher")
        self.settings = Settings()
        self._envs: list[Environment] = []

        # Use the platform's native ttk theme (no "clam" override) so that
        # ttk widgets and tk widgets blend together visually.
        self._set_window_icon()

        self._build()

        # If env_root isn't set, prompt on first run.
        if not self.settings.get("env_root"):
            self.after(100, self._prompt_env_root)
        else:
            self.refresh_environments()

        # Keyboard: Enter launches.
        self.bind("<Return>", lambda _e: self._launch())
        self.bind("<Escape>", lambda _e: self.destroy())

    # ----- Layout -----

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(1, weight=1)

        # Top bar: env root + browse.
        top = ttk.Frame(self, padding=PADDING)
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Env root:").grid(row=0, column=0, padx=(0, PADDING))
        self.env_root_var = tk.StringVar(value=self.settings.get("env_root", ""))
        entry = ttk.Entry(top, textvariable=self.env_root_var)
        entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(top, text="Browse…", command=self._browse_env_root).grid(
            row=0, column=2, padx=(PADDING, 0)
        )
        ttk.Button(top, text="Rescan", command=self.refresh_environments).grid(
            row=0, column=3, padx=(PADDING, 0)
        )

        # Three lists.
        self.env_list = self._make_list("Environment", column=0)
        self.dir_list = self._make_list("Directory", column=1)
        self.app_list = self._make_list("App", column=2)

        self.env_list.bind("<<ListboxSelect>>", lambda _e: self._on_env_select())
        self.dir_list.bind("<<ListboxSelect>>", lambda _e: self._save_last())
        self.app_list.bind("<<ListboxSelect>>", lambda _e: self._save_last())
        self.env_list.bind("<Double-Button-1>", lambda _e: self._launch())
        self.dir_list.bind("<Double-Button-1>", lambda _e: self._launch())
        self.app_list.bind("<Double-Button-1>", lambda _e: self._launch())

        # Bottom controls: one frame per column so each control aligns with
        # the list above it. Padding matches the lists' padx/pady so the
        # left and right edges line up exactly.
        bottom_left = ttk.Frame(self)
        bottom_left.grid(row=2, column=0, sticky="ew", padx=PADDING, pady=PADDING)
        self.audit_btn = ttk.Button(
            bottom_left, text="Run pip-audit", command=self._run_audit
        )
        self.audit_btn.pack(side="left")

        bottom_mid = ttk.Frame(self)
        bottom_mid.grid(row=2, column=1, sticky="ew", padx=PADDING, pady=PADDING)
        ttk.Label(bottom_mid, text="Sort:").pack(side="left")
        self.sort_var = tk.StringVar(value=self.settings.get("sort_directories_by", "alias"))
        sort_combo = ttk.Combobox(
            bottom_mid,
            textvariable=self.sort_var,
            values=["alias", "uses"],
            state="readonly",
            width=8,
        )
        sort_combo.pack(side="left", padx=(PADDING, 0))
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_sort_change())
        ttk.Button(bottom_mid, text="Edit Directories…", command=self._open_dir_editor).pack(
            side="left", padx=(PADDING, 0)
        )

        bottom_right = ttk.Frame(self)
        bottom_right.grid(row=2, column=2, sticky="ew", padx=PADDING, pady=PADDING)
        self.launch_btn = ttk.Button(bottom_right, text="Launch", command=self._launch)
        self.launch_btn.pack(side="right")

        # Status bar.
        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(PADDING, 2)).grid(
            row=3, column=0, columnspan=3, sticky="ew"
        )

        self.geometry("760x420")
        self.minsize(640, 320)

    def _make_list(self, label: str, column: int) -> tk.Listbox:
        # Plain frame (no LabelFrame) so there's no border around the list.
        # The heading is a regular label sitting above the listbox.
        frame = ttk.Frame(self, padding=PADDING)
        frame.grid(row=1, column=column, sticky="nsew", padx=PADDING, pady=PADDING)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(frame, text=label).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))

        # Flat 1px black border to match the look of ttk.Entry boxes.
        lb = tk.Listbox(
            frame,
            exportselection=False,
            activestyle="dotbox",
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="black",
            highlightcolor="black",
        )
        lb.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.grid(row=1, column=1, sticky="ns")
        return lb

    # ----- Window icon -----

    def _set_window_icon(self) -> None:
        """Use python_launcher.ico as the window/taskbar icon if present.

        Looks next to the package and next to the launcher script. On Windows
        we also set an explicit AppUserModelID so the taskbar groups the
        window under our icon instead of the generic Python one.
        """
        from pathlib import Path
        import sys

        candidates = [
            Path(__file__).parent / "python_launcher.ico",
            Path(__file__).parent.parent / "python_launcher.ico",
            Path.cwd() / "python_launcher.ico",
        ]
        ico = next((p for p in candidates if p.is_file()), None)
        if ico is None:
            return

        # Tell Windows this is its own app, otherwise the taskbar shows the
        # python.exe icon regardless of what we set on the window.
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "pylauncher.app"
                )
            except (AttributeError, OSError):
                pass

        try:
            self.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

    # ----- Refresh / state -----

    def _prompt_env_root(self) -> None:
        messagebox.showinfo(
            "First run",
            "Pick the root directory that contains your Python environments.",
            parent=self,
        )
        path = filedialog.askdirectory(parent=self, title="Env root")
        if path:
            self.env_root_var.set(path)
            self.settings.set("env_root", path)
            self.settings.save()
            self.refresh_environments()

    def _browse_env_root(self) -> None:
        path = filedialog.askdirectory(parent=self, title="Env root")
        if not path:
            return
        self.env_root_var.set(path)
        self.settings.set("env_root", path)
        self.settings.save()
        self.refresh_environments()

    # Map audit state to a foreground colour for the env list.
    _AUDIT_COLOURS = {
        "clean":      "#197a2b",   # green
        "vulnerable": "#b8860b",   # dark orange / amber
        "overdue":    "#c0392b",   # red
        "never":      "#c0392b",   # red — never audited counts as overdue
    }

    def refresh_environments(self) -> None:
        # Before listing envs, ingest any audit markers written by completed
        # pip-audit runs since the last refresh.
        self._ingest_audit_markers()

        root = self.env_root_var.get().strip()
        self.settings.set("env_root", root)
        self.settings.save()
        self._envs = discover_environments(root)
        self.env_list.delete(0, "end")
        for i, env in enumerate(self._envs):
            self.env_list.insert("end", env.name)
            state = self.settings.audit_state(env.name)
            colour = self._AUDIT_COLOURS.get(state)
            if colour:
                self.env_list.itemconfig(i, foreground=colour)

        last_env = self.settings.get("last_env", "")
        idx = next((i for i, e in enumerate(self._envs) if e.name == last_env), 0)
        if self._envs:
            self.env_list.selection_clear(0, "end")
            self.env_list.selection_set(idx)
            self.env_list.see(idx)

        self.refresh_directories()
        self._on_env_select()

        if not self._envs:
            self.status_var.set(
                f"No environments found in '{root}'." if root else "Set an env root to begin."
            )

    def refresh_directories(self) -> None:
        last_alias = self.settings.get("last_dir_alias", "")
        self.dir_list.delete(0, "end")
        dirs = self.settings.sorted_directories()
        for entry in dirs:
            self.dir_list.insert("end", entry["alias"])
        idx = next((i for i, d in enumerate(dirs) if d["alias"] == last_alias), 0)
        if dirs:
            self.dir_list.selection_clear(0, "end")
            self.dir_list.selection_set(idx)
            self.dir_list.see(idx)

    def _on_env_select(self) -> None:
        env = self._current_env()
        self.app_list.delete(0, "end")
        if env is None:
            self.audit_btn.state(["disabled"])
            return
        apps = available_apps(env)
        for a in apps:
            self.app_list.insert("end", a)
        last_app = self.settings.get("last_app", "")
        idx = apps.index(last_app) if last_app in apps else 0
        if apps:
            self.app_list.selection_clear(0, "end")
            self.app_list.selection_set(idx)
        self._save_last()
        self._update_audit_status(env)

    def _update_audit_status(self, env: Environment) -> None:
        """Update status bar + audit button based on the env's audit record."""
        # Button enabled only when pip-audit is installed in this env.
        if has_pip_audit(env):
            self.audit_btn.state(["!disabled"])
        else:
            self.audit_btn.state(["disabled"])

        rec = self.settings.get_audit(env.name)
        age = self.settings.audit_age_days(env.name)
        warn_days = int(self.settings.get("audit_warn_days", 30))

        if not has_pip_audit(env):
            self.status_var.set(
                f"{env.name}: pip-audit not installed in this env."
            )
            return
        if age is None:
            self.status_var.set(
                f"{env.name}: never audited — run pip-audit to check for vulnerabilities."
            )
            return
        status = rec.get("status") or "?"
        last = rec.get("last_run", "")
        # Trim seconds for nicer display.
        last_short = last[:16].replace("T", " ") if last else "?"
        if age > warn_days:
            self.status_var.set(
                f"{env.name}: last audit {age} days ago ({last_short}) — overdue."
            )
        elif status == "vulnerable":
            self.status_var.set(
                f"{env.name}: vulnerabilities found {age} days ago ({last_short}). Re-audit after fixing."
            )
        else:
            self.status_var.set(
                f"{env.name}: clean as of {age} day(s) ago ({last_short})."
            )

    def _on_sort_change(self) -> None:
        self.settings.set("sort_directories_by", self.sort_var.get())
        self.settings.save()
        self.refresh_directories()

    def _open_dir_editor(self) -> None:
        DirectoryEditor(self, self.settings)

    # ----- Selection helpers -----

    def _current_env(self) -> Environment | None:
        sel = self.env_list.curselection()
        if not sel:
            return None
        return self._envs[sel[0]]

    def _current_dir(self) -> dict | None:
        sel = self.dir_list.curselection()
        if not sel:
            return None
        alias = self.dir_list.get(sel[0])
        for entry in self.settings.data["directories"]:
            if entry["alias"] == alias:
                return entry
        return None

    def _current_app(self) -> str | None:
        sel = self.app_list.curselection()
        if not sel:
            return None
        return self.app_list.get(sel[0])

    def _save_last(self) -> None:
        env = self._current_env()
        d = self._current_dir()
        a = self._current_app()
        if env:
            self.settings.set("last_env", env.name)
        if d:
            self.settings.set("last_dir_alias", d["alias"])
        if a:
            self.settings.set("last_app", a)
        # Don't save on every keystroke — defer.
        # For simplicity we just save; it's a tiny file.
        self.settings.save()

    # ----- Launch -----

    def _launch(self) -> None:
        env = self._current_env()
        d = self._current_dir()
        app = self._current_app()
        if env is None:
            messagebox.showwarning("Pick an environment", "Select an environment first.", parent=self)
            return
        if d is None:
            messagebox.showwarning("Pick a directory", "Select or add a working directory.", parent=self)
            return
        if app is None:
            messagebox.showwarning("Pick an app", "Select an app to launch.", parent=self)
            return

        argv = app_command(env, app)

        # For Command Prompt, "activate" the venv by prepending Scripts to
        # PATH and setting VIRTUAL_ENV. This is exactly what activate.bat
        # does, minus the prompt-string fiddling.
        env_overrides: dict[str, str] | None = None
        if app == "Command Prompt":
            current_path = os.environ.get("PATH", "")
            env_overrides = {
                "PATH": f"{env.bin_dir}{os.pathsep}{current_path}",
                "VIRTUAL_ENV": str(env.path),
            }
            # PYTHONHOME interferes with venvs — clear it if set.
            if "PYTHONHOME" in os.environ:
                env_overrides["PYTHONHOME"] = ""

        # Console window title showing which env we're in.
        # Console window title showing which env / app this is. We set it
        # via `cmd /k "title <name> && <real exe>"` because every console-mode
        # exe on Windows (cmd, python, ipython, jupyter-lab, marimo, etc.)
        # calls SetConsoleTitle early on and would clobber STARTUPINFO.lpTitle.
        # `title` is a cmd builtin that runs *after* the child, so it wins.
        # IDLE is a Tk GUI app with no console, so it's skipped.
        title = f"{env.name} / {app}"
        console_title: str | None = None
        if sys.platform == "win32" and app != "IDLE":
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            if app == "Command Prompt":
                # The "real" command IS cmd — just set the title.
                cmdline = f"title {title}"
            else:
                inner = subprocess.list2cmdline(argv)
                cmdline = f"title {title} && {inner}"
            argv = [comspec, "/k", cmdline]

        try:
            launch(
                argv,
                d["path"],
                env_overrides=env_overrides,
                console_title=console_title,
            )
        except OSError as e:
            messagebox.showerror("Launch failed", str(e), parent=self)
            return

        self.settings.bump_directory_use(d["alias"])
        self._save_last()
        self.destroy()

    # ----- pip-audit -----

    @property
    def _markers_dir(self) -> Path:
        return CONFIG_DIR / "audit_markers"

    def _run_audit(self) -> None:
        """Launch pip-audit in a new console for the selected env.

        We invoke the bundled audit_wrapper module via the env's own python so
        pip-audit runs against the right packages. The wrapper writes a marker
        file on completion which we ingest the next time refresh_environments
        runs (or when the launcher is reopened).
        """
        env = self._current_env()
        if env is None:
            return
        if not has_pip_audit(env):
            messagebox.showinfo(
                "pip-audit not installed",
                f"pip-audit is not installed in '{env.name}'.\n\n"
                "Install it from a Command Prompt in that env:\n    pip install pip-audit",
                parent=self,
            )
            return

        pip_audit_exe = env.bin_dir / f"pip-audit{'.exe' if sys.platform == 'win32' else ''}"
        markers = self._markers_dir
        markers.mkdir(parents=True, exist_ok=True)

        # Build argv to invoke our wrapper module via the env's python.
        # Working dir is the env path itself — pip-audit doesn't care.
        argv = [
            str(env.python_exe),
            "-m", "pylauncher.audit_wrapper",
            env.name,
            str(markers),
            str(pip_audit_exe),
        ]

        # The wrapper's working dir doesn't really matter; pick the env path.
        cwd = str(env.path)

        # Same env activation as Command Prompt so pip-audit and any follow-up
        # commands the user runs (pip-audit --fix, pip list, etc.) resolve to
        # the env's tools.
        env_overrides = {
            "PATH": f"{env.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "VIRTUAL_ENV": str(env.path),
        }
        if "PYTHONHOME" in os.environ:
            env_overrides["PYTHONHOME"] = ""

        # PYTHONPATH must include this package so `python -m pylauncher.audit_wrapper`
        # works regardless of which env's python is running it.
        package_root = str(Path(__file__).parent.parent.resolve())
        existing_pp = os.environ.get("PYTHONPATH", "")
        env_overrides["PYTHONPATH"] = (
            f"{package_root}{os.pathsep}{existing_pp}" if existing_pp else package_root
        )

        # Title the console window.
        title = f"{env.name} / pip-audit"
        if sys.platform == "win32":
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            inner = subprocess.list2cmdline(argv)
            argv = [comspec, "/k", f"title {title} && {inner}"]

        try:
            launch(argv, cwd, env_overrides=env_overrides)
        except OSError as e:
            messagebox.showerror("Launch failed", str(e), parent=self)
            return

        # We don't close the launcher — the user may want to keep clicking
        # around while pip-audit runs. Schedule a marker poll to pick up the
        # result quickly once the wrapper finishes.
        if not getattr(self, "_polling_started", False):
            self._polling_started = True
            self.after(2000, self._poll_markers_then_refresh)

    def _poll_markers_then_refresh(self) -> None:
        """Check markers; if any new ones, refresh env colours/status."""
        if self._ingest_audit_markers():
            # Re-colour and refresh status for the currently selected env.
            for i, env in enumerate(self._envs):
                state = self.settings.audit_state(env.name)
                colour = self._AUDIT_COLOURS.get(state)
                if colour:
                    self.env_list.itemconfig(i, foreground=colour)
            cur = self._current_env()
            if cur:
                self._update_audit_status(cur)
        # Keep polling every few seconds while the launcher is open. pip-audit
        # itself takes time but the user might fix vulns and re-run later.
        self.after(5000, self._poll_markers_then_refresh)

    def _ingest_audit_markers(self) -> bool:
        """Read and delete any audit marker files. Return True if any were found."""
        markers = self._markers_dir
        if not markers.is_dir():
            return False
        found = False
        for f in markers.glob("*.json"):
            try:
                with f.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                env_name = data.get("env_name")
                ts = data.get("timestamp")
                status = data.get("status")
                if env_name and ts and status in ("clean", "vulnerable"):
                    self.settings.set_audit(env_name, status, ts)
                    found = True
            except (OSError, json.JSONDecodeError):
                # Skip unreadable / corrupt markers.
                pass
            try:
                f.unlink()
            except OSError:
                pass
        if found:
            self.settings.save()
        return found


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
