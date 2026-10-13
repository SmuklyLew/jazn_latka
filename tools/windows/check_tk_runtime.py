from __future__ import annotations

"""Fail-fast validation of *real* Tcl/Tk GUI startup on Windows runners.

Tcl 9 embeds support files into a ZIPFS virtual filesystem, so Python
pathlib checks are not portable. A live Tk() proves interpreter readiness.
Tk 8.6 is also checked for the menu.tcl asset that broke the Windows run.
"""

import sys


def verify_tk_runtime() -> None:
    import tkinter as tk

    for index in range(2):
        root = tk.Tk()
        try:
            root.withdraw()
            tk_version = str(root.tk.call("package", "require", "Tk"))
            if tk_version.startswith("8.6"):
                tk_library = str(root.tk.globalgetvar("tk_library"))
                menu = root.tk.call("file", "join", tk_library, "menu.tcl")
                if not bool(root.tk.call("file", "exists", menu)):
                    raise RuntimeError(f"Tk 8.6 menu.tcl missing at {menu}")
            print(
                f"Tk GUI initialization {index + 1}/2 succeeded: "
                f"Python {sys.version.split()[0]}, Tk {tk_version}, {sys.executable}",
                flush=True,
            )
        finally:
            root.destroy()


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("This Tcl/Tk CI preflight is restricted to Windows.")
    verify_tk_runtime()
