from __future__ import annotations

from pathlib import Path
import sqlite3

from latka_jazn.core.host_response_candidate_guard import build_host_generation_context
from latka_jazn.core.memory_grounded_generation_bridge import (
    build_grounded_memory_items,
    enforce_memory_grounding,
)
from latka_jazn.core.response_candidate import ResponseCandidate
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.memory_root import (
    default_memory_root,
    legacy_memory_root,
    resolve_memory_root,
)
from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


def _candidate(item_id: str) -> ResponseCandidate:
    return ResponseCandidate(
        candidate_id="candidate",
        text="Pamiętam syntetyczną bursztynową latarnię.",
        source="model_adapter",
        provider="test",
        model="test",
        status="completed",
        used_memory_item_ids=[item_id],
        generation_reason="test",
    )


def test_empty_canonical_memory_root_does_not_shadow_populated_legacy_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    canonical = default_memory_root(runtime_root)
    canonical.mkdir(parents=True)
    legacy = legacy_memory_root(runtime_root)
    legacy_db = legacy / "sqlite" / "memory_jazn.sqlite3"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_bytes(b"synthetic-memory-payload")

    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)

    assert resolve_memory_root(runtime_root) == legacy.resolve()


def test_explicit_memory_root_remains_authoritative_even_when_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    legacy = legacy_memory_root(runtime_root)
    legacy_db = legacy / "sqlite" / "memory_jazn.sqlite3"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_bytes(b"synthetic-memory-payload")

    monkeypatch.setenv("JAZN_MEMORY_ROOT", "explicit-memory")
    resolved = resolve_memory_root(runtime_root)

    assert resolved.name == "explicit-memory"
    assert resolved != legacy.resolve()


def test_v3_native_probe_requires_memory_records_fts(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(database).initialize()

    healthy = probe_unified_memory_database(database)
    assert "memory_records_fts" in healthy["required_fts_objects"]
    assert healthy["native_unified_recall_ready"] is True
    assert healthy["full_autobiographical_recall_ready"] is True

    with sqlite3.connect(database) as con:
        con.execute("DROP TABLE memory_records_fts")
        con.commit()

    degraded = probe_unified_memory_database(database)
    assert "memory_records_fts" in degraded["missing_fts_objects"]
    assert degraded["memory_search_ready"] is False
    assert degraded["native_unified_recall_ready"] is False
    assert degraded["full_autobiographical_recall_ready"] is False


def test_transactional_tier_only_is_searchable_but_not_autobiographical(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gateway = LivingMemoryGateway(tmp_path)
    monkeypatch.setattr(
        gateway,
        "discover",
        lambda: [
            {
                "source_kind": "transactional_tier_memory",
                "selected_canonical": False,
                "selected_transactional_tier": True,
                "canonical_database": str(tmp_path / "runtime_memory.sqlite3"),
                "legacy_search_ready": False,
            }
        ],
    )
    monkeypatch.setenv("JAZN_MEMORY_READINESS_POLICY", "native_unified_required")

    readiness = gateway.readiness()

    assert readiness["status"] == "ready_transactional_tier_only"
    assert readiness["memory_search_ready"] is True
    assert readiness["full_autobiographical_recall_ready"] is False
    assert readiness["memory_readiness_policy_satisfied"] is False
    assert readiness["degraded_reason"] == "transactional_tier_without_native_unified_recall"


def test_native_unified_source_satisfies_autobiographical_policy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gateway = LivingMemoryGateway(tmp_path)
    monkeypatch.setattr(
        gateway,
        "discover",
        lambda: [
            {
                "source_kind": "native_unified",
                "selected_canonical": True,
                "selected_transactional_tier": False,
                "canonical_database": str(tmp_path / "memory_jazn.sqlite3"),
                "legacy_search_ready": False,
            }
        ],
    )
    monkeypatch.setenv("JAZN_MEMORY_READINESS_POLICY", "native_unified_required")

    readiness = gateway.readiness()

    assert readiness["status"] == "ready_native_unified"
    assert readiness["memory_search_ready"] is True
    assert readiness["full_autobiographical_recall_ready"] is True
    assert readiness["memory_readiness_policy_satisfied"] is True


def test_positive_memory_claim_rejects_transactional_only_provenance() -> None:
    item_id = "tier-memory"
    grounded = build_grounded_memory_items(
        {
            "items": [
                {
                    "item_id": item_id,
                    "content": "Syntetyczna bursztynowa latarnia.",
                    "source": "runtime_write_v2/runtime_memory.sqlite3",
                    "metadata": {
                        "semantic_source_type": "active_memory",
                        "provenance_label": "pamiętam",
                        "truth_status": "source_recorded",
                        "source_locator": "memory_records:tier-memory",
                        "gateway_source_kind": "transactional_tier_memory",
                        "autobiographical_source_ready": False,
                    },
                }
            ]
        }
    )

    evaluation = enforce_memory_grounding(_candidate(item_id), grounded)

    assert evaluation.accepted is False
    assert "memory_claim_without_native_autobiographical_provenance" in evaluation.violations


def test_positive_memory_claim_accepts_native_autobiographical_provenance() -> None:
    item_id = "native-memory"
    grounded = build_grounded_memory_items(
        {
            "items": [
                {
                    "item_id": item_id,
                    "content": "Syntetyczna bursztynowa latarnia.",
                    "source": "memory/sqlite/memory_jazn.sqlite3",
                    "metadata": {
                        "semantic_source_type": "active_memory",
                        "provenance_label": "pamiętam",
                        "truth_status": "source_recorded",
                        "source_locator": "memory_records:native-memory",
                        "gateway_source_kind": "native_unified",
                        "autobiographical_source_ready": True,
                    },
                }
            ]
        }
    )

    evaluation = enforce_memory_grounding(_candidate(item_id), grounded)

    assert evaluation.accepted is True
    assert "native_autobiographical_provenance_verified" in evaluation.reasons


def test_host_context_preserves_bounded_autobiographical_provenance() -> None:
    context = {
        "nlg_plan": {"memory_policy": "required_grounded_payload"},
        "allowed_memory_items": [
            {
                "item_id": "native-memory",
                "excerpt": "Syntetyczny fragment pamięci.",
                "source": "memory/sqlite/memory_jazn.sqlite3",
                "timestamp": "2026-09-28T20:00:00+02:00",
                "confidence": 0.9,
                "relevance_reason": "synthetic test",
                "semantic_source_type": "active_memory",
                "provenance_label": "pamiętam",
                "truth_status": "source_recorded",
                "source_database": "memory/sqlite/memory_jazn.sqlite3",
                "source_locator": "memory_records:native-memory",
                "gateway_source_kind": "native_unified",
                "autobiographical_source_ready": True,
            }
        ],
    }

    host = build_host_generation_context(
        context,
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
    )
    item = host["model_context"]["allowed_memory_items"][0]

    assert item["autobiographical_source_ready"] is True
    assert item["gateway_source_kind"] == "native_unified"
    assert item["source_locator"] == "memory_records:native-memory"
    assert host["generation_contract"][
        "positive_memory_claim_requires_autobiographical_source_ready"
    ] is True
