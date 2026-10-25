"""Regression: package smoke must not poison the operator's runtime marker."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest
import subprocess
import sys

from latka_jazn.tools.release_readiness import _isolated_readiness_environment
from latka_jazn.core.runtime_root import workspace_runtime_path


def test_package_smoke_uses_only_ephemeral_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = tmp_path / "operator_state"
    original.mkdir()
    marker = original / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text(json.dumps({"active_root": "do not replace"}), encoding="utf-8")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(original))
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "PRIVATE_MEMORY")
    original_environment = dict(os.environ)
    temporary = tmp_path / "readiness" / "isolated"
    temporary.mkdir(parents=True)
    with _isolated_readiness_environment(temporary):
        assert workspace_runtime_path(temporary) == (temporary / "workspace_runtime").resolve()
        assert os.environ["JAZN_MEMORY_MODE"] == "off"
        assert "JAZN_MEMORY_ROOT" not in os.environ
        child = subprocess.run(
            [sys.executable, "-c", "import os; print(os.getenv('JAZN_RUNTIME_WORKSPACE_DIR'))"],
            capture_output=True, text=True, check=True,
        )
        assert child.stdout.strip() == str((temporary / "workspace_runtime").resolve())
    assert dict(os.environ) == original_environment
    assert json.loads(marker.read_text(encoding="utf-8")) == {"active_root": "do not replace"}
