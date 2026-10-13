from __future__ import annotations

"""Fail-fast Windows CI check for an actually usable Tcl/Tk interpreter.

Resolve asset paths from the live Tcl/Tk interpreter: Python 3.12 and 3.14
may use different Tcl layouts. Never replace or skip real GUI tests with mocks.
"""

import sys
from pathlib import Path


def verify_tk_runtime() -> None:
    import tkinter as tk

    for index in range(2):
        root = tk.Tk()  # Actual Tk load also validates all required assets.
        try:
            root.withdraw()
            tk_version = str(root.tk.call("package", "require", "Tk"))
            tcl_library = Path(str(root.tk.call("info", "library")))
            tk_library = Path(str(root.tk.globalgetvar("tk_library")))
            if not (tcl_library / "init.tcl").is_file():
                raise RuntimeError(f"Tcl {tk_version} init.tcl unavailable at {tcl_library}")
            if not (tk_library / "tk.tcl").is_file():
                raise RuntimeError(f"Tk {tk_version} tk.tcl unavailable at {tk_library}")
            if tk_version.startswith("8.6") and not (tk_library / "menu.tcl").is_file():
                raise RuntimeError(f"Tk 8.6 menu.tcl unavailable at {tk_library}")
            print(
                f"Tk initialization {index + 1}/2 succeeded: "
                f"Python {sys.version.split()[0]}, Tk {tk_version}, {sys.executable}",
                flush=True,
            )
        finally:
            root.destroy()


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("This Tcl/Tk CI preflight is restricted to Windows.")
    verify_tk_runtime()
