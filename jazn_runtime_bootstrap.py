from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import sys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jazn-runtime-bootstrap",
        description="Stdlib-only bootstrap for a verified private Jaźń Python runtime.",
        allow_abbrev=False,
    )
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--packages-relative-path", default="packages")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _sanitize_environment(runtime_root: Path) -> None:
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
    ):
        os.environ.pop(name, None)
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ["JAZN_PYTHON_RUNTIME_ACTIVE"] = "1"
    os.environ["JAZN_PYTHON_RUNTIME_ROOT"] = str(runtime_root)


def main() -> int:
    ns = _parser().parse_args()
    app_root = Path(ns.app_root).resolve()
    runtime_root = Path(ns.runtime_root).resolve()
    run_file = app_root / "run.py"
    package_root = app_root / "latka_jazn"
    if not run_file.is_file() or not package_root.is_dir():
        raise SystemExit("invalid_jazn_app_root")
    executable = Path(sys.executable).resolve()
    if not _inside(executable, runtime_root):
        raise SystemExit("python_executable_outside_declared_jazn_runtime")

    _sanitize_environment(runtime_root)

    runtime_paths: list[str] = []
    base_prefix = Path(sys.base_prefix).resolve()
    for raw in sys.path:
        if not raw:
            continue
        candidate = Path(raw).resolve()
        if _inside(candidate, runtime_root) or _inside(candidate, base_prefix):
            text = str(candidate)
            if text not in runtime_paths:
                runtime_paths.append(text)

    packages = runtime_root / str(ns.packages_relative_path)
    controlled = [str(app_root)]
    if packages.is_dir():
        controlled.append(str(packages.resolve()))
    for item in runtime_paths:
        if item not in controlled:
            controlled.append(item)
    sys.path[:] = controlled

    forwarded = list(ns.args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    sys.argv = [str(run_file), *forwarded]
    runpy.run_path(str(run_file), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
