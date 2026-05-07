"""Tiny wrapper around pip-audit that records the result for pylauncher.

Invoked as: python -m pylauncher.audit_wrapper <env_name> <markers_dir> <pip-audit-exe>

The wrapper runs pip-audit, writes a marker file describing the outcome
(env name, ISO timestamp, status), then prompts the user before exiting so
they have time to read the report and optionally run `pip-audit --fix`.

Exit code semantics from pip-audit:
    0 — no known vulnerabilities
    1 — vulnerabilities found
    other — pip-audit itself failed (network, parse error, etc.)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("Usage: audit_wrapper.py <env_name> <markers_dir> <pip-audit-exe>")
        return 2

    env_name, markers_dir, pip_audit_exe = argv[1], argv[2], argv[3]
    markers = Path(markers_dir)
    markers.mkdir(parents=True, exist_ok=True)

    print(f"=== pip-audit for env: {env_name} ===")
    print(f"Running: {pip_audit_exe}")
    print()

    try:
        rc = subprocess.call([pip_audit_exe])
    except OSError as e:
        print(f"\nFailed to launch pip-audit: {e}")
        rc = 127

    if rc == 0:
        status = "clean"
        msg = "No known vulnerabilities."
    elif rc == 1:
        status = "vulnerable"
        msg = "Vulnerabilities found. Tip: re-run with `pip-audit --fix` to auto-upgrade."
    else:
        status = "error"
        msg = f"pip-audit exited with code {rc}; result not recorded."

    if status != "error":
        marker = {
            "env_name": env_name,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": status,
        }
        # Marker filename includes a timestamp so multiple audits queue cleanly.
        ts_safe = marker["timestamp"].replace(":", "-")
        marker_path = markers / f"{env_name}__{ts_safe}.json"
        try:
            with marker_path.open("w", encoding="utf-8") as f:
                json.dump(marker, f, indent=2)
        except OSError as e:
            print(f"\nWarning: could not write marker file: {e}")

    print()
    print("=" * 60)
    print(msg)
    print("=" * 60)
    print()
    print("This window will stay open. Type `exit` or close it when done.")
    # Hand control to a shell so the user can run further commands
    # (pip-audit --fix, pip list, etc.) in the activated env.
    if sys.platform == "win32":
        os.execvp(os.environ.get("COMSPEC", "cmd.exe"), ["cmd.exe", "/k"])
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
        os.execvp(shell, [shell])
    return 0  # not reached


if __name__ == "__main__":
    sys.exit(main(sys.argv))
