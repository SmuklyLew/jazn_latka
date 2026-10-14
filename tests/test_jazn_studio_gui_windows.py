from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from latka_jazn.tools.jazn_studio import core


@pytest.mark.skipif(sys.platform != "win32", reason="Real Tk control acceptance runs on Windows CI")
def test_studio_window_navigation_and_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tkinter as tk
    from latka_jazn.tools.jazn_studio.ui import JaznStudioWindow

    root = tmp_path / "system"
    root.mkdir()
    (root / "main.py").write_text("# system")
    (root / "run.py").write_text("# thin")
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn" / "version.py").write_text("# version")
    monkeypatch.setattr(core, "workspace_runtime_path", lambda value: tmp_path / "workspace")
    window = tk.Tk()
    window.withdraw()
    try:
        studio = JaznStudioWindow(window, root)
        for page in ("dashboard", "connections", "configuration", "updates", "diagnostics", "tools"):
            studio.show(page)
            window.update_idletasks()
        assert studio.page == "tools"
        assert studio.remote_var.get().endswith(".workers.dev")
        assert studio.python_var.get() == ""
        assert len(studio.pages) == 6
        studio.closed = True
    finally:
        window.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only real Tk packaging smoke")
def test_studio_gui_script_smoke_from_checkout() -> None:
    # The public operator launcher must initialize a fresh Tcl/Tk process.
    # Reusing pytest's interpreter after a previous Tk() has been destroyed
    # is not representative of a real Windows operator launch.
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "tools/jazn_studio.py", "--gui-smoke"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, (
        f"Studio GUI subprocess exited {result.returncode}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "GUI smoke OK" in result.stdout
