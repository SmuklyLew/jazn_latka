"""Direct script packaging import regression; never builds or runs an EXE."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from tools.jazn_run_studio.build import _write_bundle_manifest
from tools.jazn_run_studio.p5_artifact_evidence import verify_frozen_bundle_manifest


def _bundle(root: Path, name: str) -> Path:
    artifact = root / name
    artifact.mkdir()
    (artifact / "JaznRunStudio.exe").write_bytes(b"synthetic-not-executable")
    (artifact / "BUILD_INFO.json").write_text(
        json.dumps({"layout": "onedir", "source_commit": "a" * 40}),
        encoding="utf-8",
    )
    return artifact


def test_module_import_generates_bundle_inventory(tmp_path: Path) -> None:
    artifact = _bundle(tmp_path, "module")
    _write_bundle_manifest(artifact)
    assert verify_frozen_bundle_manifest(artifact) == (True, 2)


def test_direct_build_script_import_without_repo_root(tmp_path: Path) -> None:
    original = Path(__file__).resolve().parents[1] / "tools" / "jazn_run_studio"
    isolated = tmp_path / "script-only"
    isolated.mkdir()
    for name in ("build.py", "p5_artifact_evidence.py"):
        shutil.copyfile(original / name, isolated / name)
    artifact = _bundle(tmp_path, "direct")
    program = (
        "from pathlib import Path; import sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "import build; assert not build.__package__; "
        "build._write_bundle_manifest(Path(sys.argv[2]))"
    )
    executed = subprocess.run(
        [sys.executable, "-I", "-c", program, str(isolated), str(artifact)],
        cwd=tmp_path, capture_output=True, text=True, timeout=20, check=False,
    )
    assert executed.returncode == 0, executed.stderr[-1500:]
    assert verify_frozen_bundle_manifest(artifact) == (True, 2)
