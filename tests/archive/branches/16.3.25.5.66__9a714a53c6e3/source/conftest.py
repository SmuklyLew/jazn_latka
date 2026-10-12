from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_workspace_for_each_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the host-level singleton isolated between independent test cases."""

    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace_runtime"))
