"""Settings management for pylauncher.

Stores config as JSON in the platform's standard config dir.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """Return the platform-appropriate config directory."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "pylauncher"
    # Linux / macOS
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "pylauncher"


CONFIG_DIR = _config_dir()
SETTINGS_PATH = CONFIG_DIR / "settings.json"


DEFAULTS: dict[str, Any] = {
    # Single root directory containing all virtual environments.
    "env_root": "",
    # List of {"alias": str, "path": str, "uses": int}
    "directories": [],
    # "alias" or "uses"
    "sort_directories_by": "alias",
    # Last selections, restored on startup for convenience.
    "last_env": "",
    "last_dir_alias": "",
    "last_app": "",
}


class Settings:
    """Tiny wrapper around a JSON settings file.

    Reads on construction, writes on save(). Missing keys fall back to DEFAULTS,
    so adding new fields in future versions doesn't break old config files.
    """

    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Merge with defaults so new keys get sensible values.
                for k, v in DEFAULTS.items():
                    self.data[k] = loaded.get(k, v)
            except (json.JSONDecodeError, OSError):
                # Corrupt or unreadable — keep defaults, don't crash.
                self.data = dict(DEFAULTS)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write: dump to temp then replace.
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        tmp.replace(self.path)

    # ----- Convenience accessors -----

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def bump_directory_use(self, alias: str) -> None:
        """Increment the use counter for a directory by alias."""
        for entry in self.data["directories"]:
            if entry["alias"] == alias:
                entry["uses"] = int(entry.get("uses", 0)) + 1
                return

    def add_directory(self, alias: str, path: str) -> bool:
        """Add a directory. Returns False if alias already exists."""
        for entry in self.data["directories"]:
            if entry["alias"] == alias:
                return False
        self.data["directories"].append(
            {"alias": alias, "path": path, "uses": 0}
        )
        return True

    def remove_directory(self, alias: str) -> None:
        self.data["directories"] = [
            d for d in self.data["directories"] if d["alias"] != alias
        ]

    def update_directory(self, old_alias: str, new_alias: str, new_path: str) -> bool:
        """Edit a directory entry. Returns False on alias collision."""
        if old_alias != new_alias:
            for entry in self.data["directories"]:
                if entry["alias"] == new_alias:
                    return False
        for entry in self.data["directories"]:
            if entry["alias"] == old_alias:
                entry["alias"] = new_alias
                entry["path"] = new_path
                return True
        return False

    def sorted_directories(self) -> list[dict]:
        sort_key = self.data.get("sort_directories_by", "alias")
        dirs = list(self.data["directories"])
        if sort_key == "uses":
            # Most-used first, ties broken alphabetically.
            dirs.sort(key=lambda d: (-int(d.get("uses", 0)), d["alias"].lower()))
        else:
            dirs.sort(key=lambda d: d["alias"].lower())
        return dirs
