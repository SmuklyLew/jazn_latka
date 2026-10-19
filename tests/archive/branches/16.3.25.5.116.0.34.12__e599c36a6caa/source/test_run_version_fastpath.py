from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from latka_jazn.version import PACKAGE_VERSION_FULL


ROOT = Path(__file__).resolve().parents[1]


def _run_version(script: Path, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(script), "--version"],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        timeout=30,
    )


def test_canonical_run_version_matches_full_release_identity() -> None:
    completed = _run_version(ROOT / "run.py", cwd=ROOT)

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert completed.stdout.strip() == PACKAGE_VERSION_FULL


def test_run_version_fast_path_does_not_import_dependency_bootstrap(tmp_path: Path) -> None:
    sandbox = tmp_path / "package"
    sandbox.mkdir()
    (sandbox / "run.py").write_text((ROOT / "run.py").read_text(encoding="utf-8"), encoding="utf-8")

    package = sandbox / "latka_jazn"
    dependencies = package / "dependencies"
    dependencies.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "version.py").write_text(
        'PACKAGE_VERSION_FULL = "isolated-version-contract"\n',
        encoding="utf-8",
    )
    (dependencies / "__init__.py").write_text("", encoding="utf-8")
    (dependencies / "runtime.py").write_text(
        'raise AssertionError("dependency bootstrap must not load for --version")\n',
        encoding="utf-8",
    )

    completed = _run_version(sandbox / "run.py", cwd=sandbox)

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert completed.stdout.strip() == "isolated-version-contract"
