"""Startup dependency evidence is interpreter-bound, optional and read-only."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.jazn_run_studio import core
from tools.jazn_run_studio.core import Settings, StudioError


ROOT = Path(__file__).resolve().parents[1]
MODULES = ("mcp", "uvicorn", "starlette", "pydantic")


def _installed(version: str = "2.2.0") -> dict[str, dict[str, object]]:
    return {
        "mcp": {"import_ok": True, "version": version},
        "uvicorn": {"import_ok": True, "version": "0.31.1"},
        "starlette": {"import_ok": True, "version": "0.48.0"},
        "pydantic": {"import_ok": True, "version": "2.12.3"},
    }


def test_mcp_preflight_uses_exact_python_and_sdk_api(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(_installed()).encode(), b"")

    monkeypatch.setattr(core, "run_external", fake_run)
    assert core.mcp_dependency_preflight("selected-mcp-python", ROOT) == {
        name: True for name in MODULES
    }
    assert calls[0][:3] == ["selected-mcp-python", "-I", "-c"]
    assert "RequestStateSecurity" in calls[0][3]
    assert "importlib.metadata.version(name)" in calls[0][3]


def test_mcp_version_incompatible_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 0, json.dumps(_installed("2.1.0")).encode(), b"")

    monkeypatch.setattr(core, "run_external", fake_run)
    checks = core.mcp_dependency_preflight("selected-mcp-python", ROOT)
    assert checks == {"mcp": False, "uvicorn": True, "starlette": True, "pydantic": True}


def test_mcp_import_missing_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _installed()
    payload["mcp"] = {"import_ok": False, "version": None}

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload).encode(), b"")

    monkeypatch.setattr(core, "run_external", fake_run)
    assert core.mcp_dependency_preflight("selected-mcp-python", ROOT)["mcp"] is False


def test_mcp_profile_without_declared_requirements_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 0, json.dumps(_installed()).encode(), b"")

    monkeypatch.setattr(core, "run_external", fake_run)
    with pytest.raises(StudioError, match="profilu MCP"):
        core.mcp_dependency_preflight("selected-mcp-python", tmp_path)


def test_optional_mcp_failures_never_block_gui_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from tools.jazn_run_studio import requirements_worker
    from latka_jazn.dependencies import common
    from latka_jazn.tools import package_integrity
    from latka_jazn.core import system_config

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='test'\nrequires-python='>=3.12'\n", encoding="utf-8"
    )
    monkeypatch.setattr(common, "resolve_profile_requirements", lambda *_a: [])
    monkeypatch.setattr(common, "inspect_current_requirements", lambda *_a: [])
    monkeypatch.setattr(package_integrity, "verify_package_integrity_manifest",
                        lambda *_a: {"ok": True, "errors": []})
    monkeypatch.setattr(system_config, "read_system_config", lambda *_a: {})
    monkeypatch.setattr(core, "load_settings", lambda *_a: (Settings(mcp_python=sys.executable), None))
    monkeypatch.setattr(core, "mcp_dependency_preflight",
                        lambda *_a: {name: False for name in MODULES})
    report = requirements_worker.inspect_requirements(tmp_path)
    assert report["required_ok"] is True
    assert report["mcp"]["ready"] is False
    assert report["mcp"]["interpreter"] == sys.executable
    rows = [item for item in report["rows"] if item["name"].startswith("MCP: ")]
    assert len(rows) == 4
    assert all(item["state"] == "OPTIONAL_MISSING" and item["required"] is False
               for item in rows)
