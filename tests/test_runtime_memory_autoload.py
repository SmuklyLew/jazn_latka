from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.bootstrap import chatgpt_recovery as recovery_module
from latka_jazn.bootstrap.chatgpt_recovery import recover_chatgpt_runtime
from latka_jazn.cli import build_parser
from tests.test_runtime_package_loader_contract import _write_installable_source


def test_runtime_bootstrap_discovers_one_memory_sidecar_and_requires_explicit_choice_for_many(
    tmp_path: Path,
) -> None:
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    first = {
        "schema_version": "jazn_package_set/v2",
        "package_name": "memory-a.zip",
        "profile": "memory",
        "archive_format": "independent",
    }
    (parts_dir / "memory-a.zip.package.json").write_text(json.dumps(first), encoding="utf-8")
    discovered = recovery_module._discover_memory_package(parts_dir)
    assert discovered["ok"] is True
    assert discovered["package_name"] == "memory-a.zip"

    second = dict(first, package_name="memory-b.zip")
    (parts_dir / "memory-b.zip.package.json").write_text(json.dumps(second), encoding="utf-8")
    ambiguous = recovery_module._discover_memory_package(parts_dir)
    assert ambiguous["ok"] is False
    assert ambiguous["state"] == "memory_package_ambiguous"
    selected = recovery_module._discover_memory_package(parts_dir, "memory-b.zip")
    assert selected["ok"] is True
    assert selected["package_name"] == "memory-b.zip"


def test_runtime_bootstrap_keeps_zip_bomb_limits_and_repackages_legacy_memory() -> None:
    gib = 1024**3
    legacy = {
        "archive_format": "binary",
        "entries": [
            {"path": "memory/raw/runtime_events.jsonl", "size_bytes": 9 * gib},
            {"path": "memory/sqlite/runtime.sqlite3", "size_bytes": 512 * 1024**2},
        ],
    }
    decision = recovery_module._memory_package_requires_v3_repack(legacy)
    assert decision["required"] is True
    assert decision["reason"] == "legacy_transport_exceeds_safe_zip_limits"
    assert decision["limits"]["max_total_uncompressed_bytes"] == 8 * gib
    assert "memory/raw/runtime_events.jsonl" in decision["oversized_members"]

    v3 = dict(legacy, memory_manifest_schema="jazn_memory_package_manifest/v3")
    assert recovery_module._memory_package_requires_v3_repack(v3)["required"] is False


def test_reused_runtime_runs_auto_memory_before_daemon_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = _write_installable_source(tmp_path / "runtime")
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    calls: list[str] = []

    monkeypatch.setattr(
        recovery_module,
        "_auto_attach_memory_before_daemon",
        lambda **_kwargs: calls.append("memory") or {"ok": True, "state": "memory_attached_ready"},
    )
    monkeypatch.setattr(
        recovery_module,
        "start_daemon",
        lambda *_args, **_kwargs: calls.append("daemon") or {"ok": True},
    )
    monkeypatch.setattr(
        recovery_module,
        "status_daemon",
        lambda *_args, **_kwargs: {"active_state": "active_trusted"},
    )
    monkeypatch.setattr(
        recovery_module,
        "_sqlite_health",
        lambda _root: {"ok": True, "database": "test.sqlite3"},
    )

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=destination,
        start_runtime_daemon=True,
        auto_attach_memory=True,
    )
    assert result.ok is True
    assert calls[:2] == ["memory", "daemon"]


def test_runtime_bootstrap_cli_supports_memory_autoload_controls() -> None:
    parser = build_parser()
    ns = parser.parse_args(
        [
            "runtime-bootstrap",
            "--parts-dir",
            "parts",
            "--destination",
            "runtime",
            "--memory-zip-name",
            "memory.zip",
            "--no-auto-memory",
        ]
    )
    assert ns.memory_zip_name == "memory.zip"
    assert ns.no_auto_memory is True
