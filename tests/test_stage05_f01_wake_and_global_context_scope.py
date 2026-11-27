"""F01/F04/F06: private wake, rest-report and global state reader boundaries."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.admission_owner_context import public_owner_digest
from latka_jazn.core.dedicated_private_context import DEDICATED_CONTEXT_ENV, DEDICATED_OWNER_ENV
from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.engine_construction import EngineRuntimeServices
from latka_jazn.memory.normalization_sidecar import MemoryNormalizationSidecar, _connect_readonly
from latka_jazn.memory.rest_cycle_store import RestCycleStore
from latka_jazn.memory.rest_wake_report import RestWakeReportBuilder, load_latest_rest_wake_report
from latka_jazn.memory.wake_state_runtime import WakeStateRuntimeBridge


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bind: Any, *, name: str) -> Path:
    root = tmp_path / name
    (root / "local_resources").mkdir(parents=True)
    bind(root, "alice", None)
    for var in ("JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_MEMORY_ROOT",
                "JAZN_MEMORY_SOURCE_ROOTS", "JAZN_MEMORY_TIER_DB", "JAZN_REST_CYCLE_DB",
                "JAZN_NORMALIZATION_SIDECAR_DB"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(DEDICATED_CONTEXT_ENV, "dedicated_root")
    monkeypatch.setenv(DEDICATED_OWNER_ENV, public_owner_digest("alice"))
    monkeypatch.setenv("JAZN_MEMORY_SYNC_MODE", "off")
    return root.resolve()


def _marker(path: Path, label: str) -> None:
    with closing(sqlite3.connect(path)) as con:
        con.execute("CREATE TABLE canary(value TEXT)")
        con.execute("INSERT INTO canary VALUES(?)", (label,))
        con.commit()


@pytest.mark.parametrize("names", [("state#alice.sqlite3", "state"),
                                   ("state%20alice.sqlite3", "state alice.sqlite3")])
@pytest.mark.parametrize("immutable", [False, True])
def test_normalization_uri_never_opens_other_file(
    tmp_path: Path, names: tuple[str, str], immutable: bool,
) -> None:
    intended, alias = (tmp_path / name for name in names)
    _marker(intended, "alice-private")
    _marker(alias, "foreign-synthetic")
    before = intended.read_bytes(), alias.read_bytes()
    with closing(_connect_readonly(intended, immutable=immutable)) as con:
        assert con.execute("SELECT value FROM canary").fetchone()[0] == "alice-private"
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            con.execute("INSERT INTO canary VALUES('forbidden')")
    assert (intended.read_bytes(), alias.read_bytes()) == before


def test_wake_and_rest_roundtrip_in_literal_scoped_root_and_memory_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    root = _root(tmp_path, monkeypatch, stage05_public_context, name="scope#alice%20")
    alias = tmp_path / "scope"
    _marker(alias, "foreign-synthetic")
    before = alias.read_bytes()
    raw = root / "memory" / "raw"
    raw.mkdir(parents=True)
    (raw / "dziennik.json").write_text("[]", encoding="utf-8")
    config = JaznConfig(root=root, memory_mode="optional")
    source = config.recovered_memory_db_path
    source.parent.mkdir(parents=True, exist_ok=True)
    content = "synthetic-alice-memory"
    with closing(sqlite3.connect(source)) as con:
        con.executescript("""
            CREATE TABLE messages(
                message_id TEXT, conversation_id TEXT, conversation_title TEXT, role TEXT,
                timestamp TEXT, content_text TEXT, content_hash TEXT, first_source_file TEXT,
                first_source_sha256 TEXT, source_refs_json TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        con.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
            "m1", "c1", "Synthetic", "user", "2026-07-16T10:00:00+00:00", content,
            hashlib.sha256(content.encode()).hexdigest(), "synthetic.json", "a" * 64, "[]",
            "2026-07-16T10:00:00+00:00", "2026-07-16T10:00:00+00:00",
        ))
        con.commit()
    assert config.memory_availability.persistent_memory_enabled is True
    sidecar = MemoryNormalizationSidecar(
        root, source_db_path=source, sidecar_db_path=config.normalization_sidecar_db_path,
        runtime_version=config.version,
    )
    prepared = sidecar.prepare(deep_verify=True).to_dict()
    assert prepared["status"] == "ready", prepared
    with RestCycleStore(config.rest_cycle_db_path) as store:
        episode = store.start_episode(
            trigger="test", continuity_mode="retrieval_only", continuity_claim_allowed=False,
            shadow_mode=True, started_at_utc="2026-08-11T20:00:00+00:00", started_monotonic_ns=100,
        )
        cycle = store.begin_cycle(
            episode_id=episode, ordinal=1, idle_seconds=900,
            started_at_utc="2026-08-11T20:15:00+00:00", started_monotonic_ns=200,
        )
        store.finish_cycle(
            cycle, status="skipped", ended_at_utc="2026-08-11T20:15:01+00:00", ended_monotonic_ns=300,
            phase_reached=3, model_status="model_unavailable", error=None, payload={"reason": "model_unavailable"},
        )
        store.finish_episode(
            episode, status="completed", ended_at_utc="2026-08-11T21:00:00+00:00", ended_monotonic_ns=400,
        )
        report = RestWakeReportBuilder(store).build_and_persist(episode)
    assert load_latest_rest_wake_report(config.rest_cycle_db_path)["report_sha256"] == report["report_sha256"]
    wake = WakeStateRuntimeBridge(config).load()
    assert wake.status == "ready", wake.errors
    assert wake.snapshot_id == prepared["wake_state"]["active_snapshot"]["snapshot_id"]
    assert wake.rest_report is not None and wake.rest_report["report_sha256"] == report["report_sha256"]
    assert wake.context is not None and "foreign-synthetic" not in repr(wake.context)
    protected = (source, config.normalization_sidecar_db_path, config.memory_tier_db_path, config.rest_cycle_db_path)
    snapshot = [(p.exists(), p.read_bytes() if p.exists() else None) for p in protected]
    disabled = WakeStateRuntimeBridge(JaznConfig(root=root, memory_mode="off"))
    blocked = disabled.hydrate_l1(session_id="synthetic-off")
    assert blocked.status == "memory_disabled_by_policy" and blocked.context is None
    assert blocked.continuity_claim_allowed is False and blocked.ordinary_dialogue_allowed is True
    assert disabled.end_session("synthetic-off") == 0
    assert [(p.exists(), p.read_bytes() if p.exists() else None) for p in protected] == snapshot
    assert alias.read_bytes() == before


@pytest.mark.parametrize("kind", ["hardlink", "symlink"])
def test_global_state_alias_refused_before_hydration_or_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any, kind: str,
) -> None:
    root = _root(tmp_path, monkeypatch, stage05_public_context, name="alice")
    config = JaznConfig(root=root, memory_mode="off")
    path = config.runtime_workspace_dir / "runtime_state.json"
    path.parent.mkdir(parents=True)
    other = tmp_path / "foreign-state.json"
    other.write_text(json.dumps({"last_user_text": "foreign-synthetic"}), encoding="utf-8")
    before = other.read_bytes()
    try:
        if kind == "hardlink":
            os.link(other, path)
        else:
            path.symlink_to(other)
    except OSError as exc:
        pytest.skip(f"filesystem does not support requested link: {type(exc).__name__}")
    services = EngineRuntimeServices(config)
    with pytest.raises(ValueError, match="private_context_.*(link|alias)"):
        services.build_dependencies()
    services.runtime_state_path = path
    with pytest.raises(ValueError, match="private_context_.*(link|alias)"):
        services.hydrate()
    engine = object.__new__(JaznEngine)
    engine.config = config
    engine.runtime_state_path = path
    with pytest.raises(ValueError, match="private_context_.*(link|alias)"):
        engine._load_runtime_state()
    engine._save_runtime_state()
    assert other.read_bytes() == before
    assert path.read_bytes() == before
