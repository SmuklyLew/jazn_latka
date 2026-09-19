from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.core.cognitive_runtime_coordinator import CognitiveRuntimeCoordinator
from latka_jazn.core.homeostasis import HomeostasisInput
from latka_jazn.core.knowledge_fabric import KnowledgeFabric
from latka_jazn.core.runtime_turn_contract import RuntimeTurnContract
from latka_jazn.core.scientific_basis import reference_by_key
from latka_jazn.core.self_architecture_audit import SelfArchitectureAuditor
from latka_jazn.memory.dream_sandbox import DreamSandbox
from latka_jazn.memory.memory_recovery_pipeline import MemoryRecoveryPipeline
from latka_jazn.memory.rest_replay import RestReplayEngine


def test_recovery_snapshot_is_not_runtime_write_target(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    cfg.recovered_memory_db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.recovered_memory_db_path.write_bytes(b"snapshot")
    assert cfg.normalization_source_db_path == cfg.recovered_memory_db_path
    assert cfg.memory_db_path == cfg.runtime_write_db_path
    assert cfg.memory_db_path_readonly == cfg.runtime_write_db_path_readonly
    assert cfg.memory_db_path != cfg.recovered_memory_db_path


def _build_normalized_sidecar(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE normalization_runs(
              run_id TEXT PRIMARY KEY, started_at_utc TEXT, ended_at_utc TEXT,
              status TEXT, coverage_complete INTEGER
            );
            CREATE TABLE normalized_memory_items(
              item_id TEXT PRIMARY KEY, memory_type TEXT, source_table TEXT,
              source_row_id TEXT, conversation_id TEXT, message_id TEXT,
              source_timestamp TEXT, source_file TEXT, source_sha256 TEXT,
              content_excerpt TEXT, content_hash TEXT, truth_status TEXT,
              confidence REAL, importance REAL, memory_namespace TEXT,
              source_evidence_json TEXT, updated_at_utc TEXT, run_id TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO normalization_runs VALUES(?,?,?,?,?)",
            ("run-1", "2026-08-11T00:00:00+00:00", "2026-08-11T00:01:00+00:00", "ok", 1),
        )
        for idx, domain in enumerate(("book", "relationship", "runtime"), start=1):
            text = f"Zweryfikowane wspomnienie numer {idx} z domeny {domain}."
            con.execute(
                "INSERT INTO normalized_memory_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"item-{idx}", "conversation_message", "legacy_messages", str(idx),
                    f"conv-{idx}", f"msg-{idx}", f"2026-08-{idx:02d}T00:00:00+00:00",
                    "memory/source", f"sha-{idx}", text, f"hash-{idx}", "source_recorded",
                    0.9, 0.8, domain, json.dumps({"source": "fixture"}),
                    f"2026-08-{idx:02d}T00:00:00+00:00", "run-1",
                ),
            )


def test_rest_replay_reads_individual_normalized_records(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    _build_normalized_sidecar(cfg.normalization_sidecar_db_path)
    items = RestReplayEngine(cfg).select(limit=3)
    assert len(items) == 3
    assert {item.source_memory_id for item in items} == {"item-1", "item-2", "item-3"}
    assert all(item.source_tier == "normalized_l1" for item in items)
    assert all(item.provenance["normalization_run_id"] == "run-1" for item in items)


def test_dream_readiness_separates_scheduler_from_generator(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path, model_adapter="null", rest_local_model_enabled=True)
    unavailable = DreamSandbox(cfg).readiness()
    assert unavailable["rest_dream_ready"] is False
    injected = DreamSandbox(cfg, generator=lambda *_: "symulacja").readiness()
    assert injected["rest_dream_ready"] is True


def test_homeostasis_control_effect_reaches_model_request(tmp_path: Path) -> None:
    plan = CognitiveRuntimeCoordinator().plan_turn(
        user_text="Zweryfikuj konfliktujące źródła.",
        explicit_intent="system_update_execution_request",
        homeostasis_input=HomeostasisInput(source_conflict=0.95, uncertainty=0.9, truth_need=1.0),
        classifier_confidence=0.5,
        source_available=True,
        tool_available=True,
    )
    assert plan["control_effects"]["generation_limit"] is not None
    contract = RuntimeTurnContract.for_model_request(
        user_text="test",
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        runtime_exact_text="fallback",
        system_context={"cognitive_runtime_plan": plan},
    )
    request = contract.to_model_adapter_request(
        user_text="test",
        system_context={"cognitive_runtime_plan": plan},
    )
    assert request.max_output_tokens == plan["control_effects"]["generation_limit"]
    assert request.metadata["cognitive_control_enforced"] is True
    assert request.metadata["cognitive_generation_limit_enforced"] is True


def test_knowledge_fabric_wraps_already_authorized_runtime_evidence() -> None:
    evidence = KnowledgeFabric.evidence_from_memory_context(
        {
            "conversation_archive_hits": [
                {
                    "message_uid": "m1",
                    "excerpt": "Źródłowy fragment rozmowy.",
                    "source_locator": "archive:m1",
                    "grounding": "conversation_archive_v1+fts_v1",
                    "confidence": 0.88,
                }
            ]
        },
        limit=2,
    )
    assert len(evidence) == 1
    assert evidence[0].source_locator == "archive:m1"
    assert evidence[0].provenance["runtime_memory_gate"] is True


def test_scientific_map_source_keys_are_resolvable() -> None:
    assert reference_by_key("pmc_interacting_brain_systems_memory_consolidation") is not None
    assert reference_by_key("pmc_hippocampus_prefrontal_amygdala_learning_memory") is not None
    clin = reference_by_key("clin_continual_learning")
    assert clin is not None
    assert clin["title"].startswith("CLIN: A Continually Learning Language Agent")


def test_self_architecture_presence_is_not_reported_as_behavior_verified(tmp_path: Path) -> None:
    for rel in ("main.py", "latka_jazn/core/engine.py", "latka_jazn/core/route_registry.py"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")
    check = SelfArchitectureAuditor(tmp_path)._check_capability(
        "runtime_core",
        ["main.py", "latka_jazn/core/engine.py", "latka_jazn/core/route_registry.py"],
        "runtime",
    )
    assert check.status == "present_unverified"
    assert "not behavioral evidence" in check.risk_or_gap


def test_canonical_archive_partial_blocks_wake_pipeline(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runtime"
    manifest = root / "memory/sqlite/conversation_archive_v1/conversation_archive_manifest.sqlite3"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(manifest) as con:
        con.execute("CREATE TABLE manifest_meta(key TEXT PRIMARY KEY, value TEXT)")
        con.execute("CREATE TABLE shard_files(shard_id TEXT PRIMARY KEY, family TEXT, ordinal INTEGER, relative_path TEXT)")
    pipeline = MemoryRecoveryPipeline(root)
    fake = SimpleNamespace(ok=True, errors=[], to_dict=lambda: {"status": "ready", "ok": True})
    monkeypatch.setattr(pipeline.recovery, "rebuild", lambda **_: fake)
    report = pipeline.run()
    assert report.status == "archive_not_searchable"
    assert "conversation_archive_not_searchable" in report.errors
