"""Explicit onedir build; never installs dependencies or downloads tools."""
from __future__ import annotations

import argparse
import os
import json
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True, help="New artifact parent directory")
    parser.add_argument("--console", action="store_true", help="Diagnostic build with console output")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    argv = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--console" if args.console else "--windowed",
            "--name", "JaznRunStudio", "--distpath", str(output / "dist"),
            "--workpath", str(output / "build"), "--specpath", str(output),
            "--paths", str(root), str(root / "jazn_run_studio.py")]
    argv[3:3] = ["--copy-metadata", "PySide6-Essentials", "--copy-metadata", "shiboken6"]
    env = dict(os.environ)
    if os.name == "nt":
        # Dependency scanning must not pick Git/other tools' incompatible ICU
        # DLLs ahead of the Windows system ICU used by the Qt wheel itself.
        from importlib.util import find_spec
        qt = find_spec("PySide6")
        if qt is None or qt.origin is None:
            raise RuntimeError("Build requires the optional run-studio dependency")
        windows = Path(os.environ["SystemRoot"])
        env["PATH"] = os.pathsep.join(map(str, [Path(sys.executable).parent,
            Path(sys.base_prefix), windows / "System32", windows,
            Path(qt.origin).parent]))
    code = subprocess.run(argv, cwd=root, env=env, shell=False, check=False).returncode
    if code == 0:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                              text=True, shell=False, check=False)
        artifact = output / "dist" / "JaznRunStudio"
        # A mocked compiler used by unit tests does not create an artifact.
        if artifact.is_dir():
            info = {"source_commit": head.stdout.strip() if head.returncode == 0 else None,
                    "python": sys.version, "qt_binding": version("PySide6-Essentials"),
                    "pyinstaller": version("pyinstaller"), "layout": "onedir",
                    "qt_license_notices": "_internal/*dist-info/licenses/"}
            (artifact / "BUILD_INFO.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
            from tools.jazn_run_studio.p5_artifact_evidence import write_frozen_bundle_manifest
            write_frozen_bundle_manifest(artifact)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
