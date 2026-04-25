"""Tkinter UI for pylauncher.

Layout:
    [ Environments ] [ Directories ] [ Apps ]
    [ status / sort toggle / edit dirs / launch ]
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path

from .settings import Settings
from .discovery import discover_environments, available_apps, app_command, Environment
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

        # Try a slightly nicer default theme where available.
        try:
            ttk.Style(self).theme_use("clam")
        except tk.TclError:
            pass

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

        # Bottom bar: sort toggle, edit dirs, launch.
        bottom = ttk.Frame(self, padding=PADDING)
        bottom.grid(row=2, column=0, columnspan=3, sticky="ew")
        bottom.columnconfigure(2, weight=1)

        ttk.Label(bottom, text="Sort dirs by:").grid(row=0, column=0)
        self.sort_var = tk.StringVar(value=self.settings.get("sort_directories_by", "alias"))
        sort_combo = ttk.Combobox(
            bottom,
            textvariable=self.sort_var,
            values=["alias", "uses"],
            state="readonly",
            width=8,
        )
        sort_combo.grid(row=0, column=1, padx=(PADDING, 0))
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_sort_change())

        ttk.Button(bottom, text="Edit Directories…", command=self._open_dir_editor).grid(
            row=0, column=2, padx=PADDING
        )

        self.launch_btn = ttk.Button(bottom, text="Launch", command=self._launch)
        self.launch_btn.grid(row=0, column=3, sticky="e")

        # Status bar.
        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(PADDING, 2)).grid(
            row=3, column=0, columnspan=3, sticky="ew"
        )

        self.geometry("760x420")
        self.minsize(640, 320)

    def _make_list(self, label: str, column: int) -> tk.Listbox:
        frame = ttk.LabelFrame(self, text=label, padding=PADDING)
        frame.grid(row=1, column=column, sticky="nsew", padx=PADDING, pady=PADDING)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        lb = tk.Listbox(frame, exportselection=False, activestyle="dotbox")
        lb.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")
        return lb

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

    def refresh_environments(self) -> None:
        root = self.env_root_var.get().strip()
        self.settings.set("env_root", root)
        self.settings.save()
        self._envs = discover_environments(root)
        self.env_list.delete(0, "end")
        for env in self._envs:
            self.env_list.insert("end", env.name)

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
        else:
            self.status_var.set(f"{len(self._envs)} environment(s) found.")

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
        try:
            launch(argv, d["path"])
        except OSError as e:
            messagebox.showerror("Launch failed", str(e), parent=self)
            return

        self.settings.bump_directory_use(d["alias"])
        self._save_last()
        self.destroy()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
