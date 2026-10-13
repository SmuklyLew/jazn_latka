from __future__ import annotations

"""Fail-fast Windows CI check for a complete, usable Tcl/Tk distribution.

Execute real Tk windows rather than skipping UI tests or using a dummy display.
"""

import sys
from pathlib import Path


def verify_tk_runtime() -> None:
    import tkinter as tk

    prefix = Path(sys.base_prefix)
    tcl_dir = prefix / "tcl"
    required_globs = ("tcl*/init.tcl", "tk*/tk.tcl", "tk*/menu.tcl")
    missing = [pattern for pattern in required_globs if not list(tcl_dir.glob(pattern))]
    if missing:
        raise RuntimeError(
            f"Incomplete Tcl/Tk distribution under {tcl_dir}: missing " + ", ".join(missing)
        )
    for index in range(2):
        root = tk.Tk()
        try:
            root.withdraw()
            assert root.tk.call("package", "require", "Tk")
            print(f"Tk initialization {index + 1}/2 succeeded: {sys.executable}", flush=True)
        finally:
            root.destroy()


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("This Tcl/Tk CI preflight is restricted to Windows.")
    verify_tk_runtime()
