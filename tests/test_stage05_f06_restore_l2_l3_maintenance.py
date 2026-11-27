"""F06: every mutating verified-restore phase requires the same maintenance gate."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.core.runtime_root import RuntimeWorkspaceBusyError, runtime_memory_transition_lock
from latka_jazn.tools import verified_memory_restore as restore


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "synthetic-root"
    (root / "local_resources").mkdir(parents=True)
    return root


@pytest.mark.parametrize("phase", ["l2", "l3"])
def test_mutating_restore_phase_cannot_run_during_another_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str,
) -> None:
    root = _root(tmp_path)
    def forbidden(*_a: Any, **_k: Any) -> Any:
        pytest.fail("busy maintenance must reject before live status or data access")
    monkeypatch.setattr(restore, "_require_quiescent_runtime", forbidden)
    with runtime_memory_transition_lock(root):
        with pytest.raises(restore.VerifiedMemoryRestoreError, match="runtime_memory_transition_busy"):
            if phase == "l2":
                restore.apply_l2_review(root, manifest_path=root / "manifest.json",
                                        expected_sha256="0" * 64, reviewed_by="synthetic", l3_limit=1)
            else:
                restore.activate(root, l3_manifest_path=root / "manifest.json",
                                 expected_sha256="0" * 64, approved_by="synthetic",
                                 start_daemon=True, report_path=None)


@pytest.mark.parametrize("phase", ["l2", "l3"])
def test_restore_requires_quiescence_while_holding_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str,
) -> None:
    root = _root(tmp_path)
    def observe(_root: Path) -> dict[str, Any]:
        with pytest.raises(RuntimeWorkspaceBusyError):
            with runtime_memory_transition_lock(root):
                pytest.fail("status observation outside maintenance lock")
        raise restore.VerifiedMemoryRestoreError("synthetic live daemon")
    monkeypatch.setattr(restore, "_require_quiescent_runtime", observe)
    with pytest.raises(restore.VerifiedMemoryRestoreError, match="synthetic live daemon"):
        if phase == "l2":
            restore.apply_l2_review(root, manifest_path=root / "manifest.json",
                                    expected_sha256="0" * 64, reviewed_by="synthetic", l3_limit=1)
        else:
            restore.activate(root, l3_manifest_path=root / "manifest.json",
                             expected_sha256="0" * 64, approved_by="synthetic",
                             start_daemon=True, report_path=None)
    with runtime_memory_transition_lock(root):
        pass
