from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from latka_jazn.tools.memory_rebuild_app.protocol_engine import ProtocolEngine
from latka_jazn.version import PACKAGE_VERSION


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("broken", ["build_a", "build_b", "projection_a", "projection_b", "missing_build"])
def test_test03_rejects_failed_build_even_when_snapshots_match(tmp_path: Path, wrapped: bool, broken: str) -> None:
    engine = ProtocolEngine(tmp_path, system_version=PACKAGE_VERSION, base_commit="synthetic")
    build = {"initialized": {"ok": True}, "import": {"ok": True}, "validation": {"ok": True}}
    report = {"source_union": {"ok": True, "requires_projection_resolution": False},
              "semantic_reconciliation": True,
              "build_a": deepcopy(build), "build_b": deepcopy(build),
              "projection_a": {"ok": True, "raw_l0_unchanged": True},
              "projection_b": {"ok": True, "raw_l0_unchanged": True}}
    if broken == "missing_build":
        del report["build_a"]
    elif broken.startswith("build_"):
        report[broken]["import"]["ok"] = False
    else:
        report[broken]["ok"] = False
    payload = {"details": report} if wrapped else report
    result = engine.validate_test03(payload)
    assert result["ok"] is False, "Matching partial snapshots cannot certify failed reconstruction"
    assert result["blockers"]
    checks = {check["name"]: check["passed"] for check in result["checks"]}
    assert checks["normal_reverse_semantic_reconciliation"] is True
