from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import daemon_autostart, runtime_daemon
from latka_jazn.core.chat_command_contract import build_chatgpt_host_presentation_packet
from latka_jazn.core.chatgpt_host_pending_store import issue_continuation_token
from latka_jazn.core.chatgpt_host_pre_response_gate import run_host_pre_response_gate
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.core.memory_recall_presenter import MemoryRecallPresenter
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.runtime_root import active_runtime_marker_path
from latka_jazn.core.runtime_session import JaznRuntimeSession, _host_finalization_pending
from latka_jazn.mcp.tools import jazn_finalize_reply, jazn_generate_visible_reply
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import (
    MemoryKind,
    MemoryTier,
    MemoryTruthStatus,
    SourceEvidence,
    WorkingMemoryRecord,
    deterministic_memory_id,
)
from latka_jazn.memory.memory_recall_contract import MemoryRecallContractBuilder
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.runtime_memory_install import resolve_memory_tier_database_path


HEADER = "🕒 2026-08-28 12:00:00"
MEMORY_TEXT = f"{HEADER}\n🌿 Łatka\nPamiętam syntetyczny bursztynowy kompas."


def _memory_observability(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "memory_recall_requested": True,
        "memory_recall_executed": True,
        "memory_search_ready": True,
        "memory_recall_status": "valid_grounded_recall",
        "memory_source_count": 1,
        "memory_provenance_available": True,
        "memory_source_types": ["active_memory"],
        "runtime_turn_id": "turn-memory-v16323",
        "trace_id": "trace-memory-v16323",
        "selected_transport": "persistent_daemon",
        "fallback_reason": "daemon_reused",
        "requested_runtime_root": "/runtime_A",
        "resolved_active_root": "/runtime_B",
        "daemon_endpoint_root": "/runtime_B",
        "daemon_identity_verified": True,
    }
    payload.update(overrides)
    return payload


def _memory_response(
    observability: dict[str, Any] | None = None,
    *,
    include_observability: bool = True,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "type": "chatgpt_host_presentation",
        "action": "display_exact",
        "phase": "runtime_final_available",
        "turn_id": "turn-memory-v16323",
        "trace_id": "trace-memory-v16323",
        "final_visible_text": MEMORY_TEXT,
        "chatgpt_host_bridge": {
            "turn_id": "turn-memory-v16323",
            "trace_id": "trace-memory-v16323",
            "required_visible_prefix": HEADER,
        },
        "transport_observability": {
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "requested_runtime_root": "/runtime_A",
            "resolved_active_root": "/runtime_B",
            "daemon_endpoint_root": "/runtime_B",
            "daemon_identity_verified": True,
            "daemon_reused": True,
            "daemon_started": False,
            "one_shot_verified": False,
        },
    }
    if include_observability:
        response["memory_recall_observability"] = observability or _memory_observability()
    return response


def test_frozen_recall_contract_preserves_typed_provenance() -> None:
    context = {
        "living_memory_search": {
            "status": "ready_transactional_tier_only",
            "memory_search_ready": True,
        },
        "counts": {"living_memory_hits": 1},
        "memory_recall_payload": {
            "items": [
                {
                    "item_type": "living_memory:runtime_write_v2:working",
                    "content_excerpt": "Syntetyczne wspomnienie o bursztynowym kompasie.",
                    "source": "synthetic.sqlite3 / memory_records:memory-v16323",
                    "semantic_source_type": "active_memory",
                    "provenance_label": "pamiętam",
                    "truth_status": "source_recorded",
                    "metadata": {
                        "source_layer": "runtime_write_v2:working",
                        "source_locator": "memory_records:memory-v16323",
                    },
                }
            ]
        },
    }

    contract = MemoryRecallContractBuilder().build(
        context,
        user_text="Przypomnij sobie bursztynowy kompas.",
    ).to_dict()

    assert len(contract["items"]) == 1
    item = contract["items"][0]
    assert item["metadata"]["semantic_source_type"] == "active_memory"
    assert item["metadata"]["provenance_label"] == "pamiętam"
    assert item["metadata"]["truth_status"] == "source_recorded"
    assert item["metadata"]["source_locator"] == "memory_records:memory-v16323"


def test_transactional_runtime_write_hit_is_typed_as_active_memory() -> None:
    payload = MemoryRecallPresenter().build_payload(
        {
            "query_terms": ["bursztynowy", "kompas"],
            "living_memory_hits": [
                {
                    "source_layer": "runtime_write_v2:working",
                    "source_database": "memory/sqlite/runtime_write_v2/runtime_memory.sqlite3",
                    "source_locator": "memory_records:memory-v16323",
                    "content_excerpt": "Syntetyczny zapis pamięci: bursztynowy kompas.",
                    "truth_status": "source_recorded",
                    "confidence": 0.97,
                    "importance": 0.91,
                    "relevance": 0.99,
                    "grounding": "read_only_runtime_write_v2_gateway",
                    "metadata": {
                        "source_layer": "runtime_write_v2",
                        "tier": "working",
                        "evidence_sources": [
                            {
                                "source_type": "manual_issue_180_seed",
                                "source_id": "issue-180:turn-source",
                            }
                        ],
                    },
                }
            ],
            "counts": {"living_memory_hits": 1},
        },
        user_text="Przypomnij sobie bursztynowy kompas.",
    )

    assert len(payload["items"]) == 1
    assert payload["items"][0]["semantic_source_type"] == "active_memory"
    assert payload["items"][0]["provenance_label"] == "pamiętam"


@pytest.mark.parametrize(
    ("observability", "expected_reason"),
    [
        (
            _memory_observability(
                memory_recall_executed=False,
                memory_search_ready=False,
                memory_recall_status="recall_not_executed",
                memory_source_count=0,
                memory_provenance_available=False,
                memory_source_types=[],
            ),
            "memory_recall_required_not_executed",
        ),
        (
            _memory_observability(
                memory_search_ready=False,
                memory_recall_status="memory_not_ready",
                memory_source_count=0,
                memory_provenance_available=False,
                memory_source_types=[],
            ),
            "active_memory_not_ready",
        ),
        (
            _memory_observability(
                memory_recall_status="memory_recall_unavailable",
                memory_source_count=0,
                memory_provenance_available=False,
                memory_source_types=[],
            ),
            "active_memory_unavailable",
        ),
        (
            _memory_observability(
                memory_recall_status="recall_provenance_unavailable",
                memory_provenance_available=False,
                memory_source_types=["unknown"],
            ),
            "memory_recall_provenance_unavailable",
        ),
    ],
)
def test_required_recall_truth_failures_are_host_diagnostic(
    observability: dict[str, Any],
    expected_reason: str,
) -> None:
    result = run_host_pre_response_gate(
        "Przypomnij sobie bursztynowy kompas.",
        invoke_runtime=lambda _text: _memory_response(observability),
        requested_runtime_root="/runtime_A",
    )

    assert result["ok"] is False
    assert result["action"] == "host_diagnostic"
    assert result["visible_output_source"] == "host_diagnostic"
    assert result["diagnostic_reason"] == expected_reason
    assert "🌿 Łatka" not in result["visible_text"]
    assert MEMORY_TEXT not in result["visible_text"]


def test_host_context_cannot_substitute_for_runtime_recall_execution() -> None:
    response = _memory_response(include_observability=False)
    response["host_generation_context"] = {
        "allowed_memory_items": [
            {
                "content": "Tekst znany wyłącznie hostowi.",
                "source": "host_project_context",
            }
        ]
    }

    result = run_host_pre_response_gate(
        "Co pamiętasz jako pierwsze?",
        invoke_runtime=lambda _text: response,
        requested_runtime_root="/runtime_A",
    )

    assert result["ok"] is False
    assert result["action"] == "host_diagnostic"
    assert result["diagnostic_reason"] == "memory_recall_observability_missing"
    assert result["visible_output_source"] == "host_diagnostic"
    assert "🌿 Łatka" not in result["visible_text"]


def test_canonical_visible_reply_tool_cannot_substitute_host_context_for_recall() -> None:
    response = _memory_response(include_observability=False)
    response["runtime_truth_gate"] = {"ok": True, "normal_response_allowed": True}
    response["final_visible_integrity"] = {"valid": True}
    response["host_generation_context"] = {
        "allowed_memory_items": [
            {"content": "Tekst znany wyłącznie hostowi.", "source": "host_context"}
        ]
    }

    class Gateway:
        runtime_root = "/runtime_A"

        def chat(self, message: str, *, session_id: str | None = None) -> dict[str, Any]:
            assert message == "Co pamiętasz jako pierwsze?"
            return response

        def issue_continuation(self, _response: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("failed recall gate cannot issue continuation")

    result = jazn_generate_visible_reply.run(
        Gateway(),
        message="Co pamiętasz jako pierwsze?",
    )

    assert result["isError"] is True
    assert result["structuredContent"]["action"] == "host_diagnostic"
    assert result["structuredContent"]["reason"] == "memory_recall_observability_missing"
    assert result["structuredContent"]["visible_output_source"] == "host_diagnostic"
    assert MEMORY_TEXT not in result["content"][0]["text"]


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"runtime_turn_id": "stale-turn"}, "memory_recall_turn_id_mismatch"),
        ({"trace_id": "stale-trace"}, "memory_recall_trace_id_mismatch"),
    ],
)
def test_stale_recall_result_is_fail_closed(
    overrides: dict[str, Any],
    expected_reason: str,
) -> None:
    result = run_host_pre_response_gate(
        "Przypomnij sobie bursztynowy kompas.",
        invoke_runtime=lambda _text: _memory_response(_memory_observability(**overrides)),
        requested_runtime_root="/runtime_A",
    )

    assert result["ok"] is False
    assert result["diagnostic_reason"] == expected_reason
    assert result["visible_output_source"] == "host_diagnostic"


def test_active_transport_lost_between_turns_is_fail_closed() -> None:
    response = _memory_response(_memory_observability(daemon_identity_verified=False))
    response["transport_observability"]["daemon_identity_verified"] = False

    result = run_host_pre_response_gate(
        "Przypomnij sobie bursztynowy kompas.",
        invoke_runtime=lambda _text: response,
        requested_runtime_root="/runtime_A",
    )

    assert result["ok"] is False
    assert result["diagnostic_reason"] == "daemon_identity_not_verified"
    assert result["visible_output_source"] == "host_diagnostic"


def test_blocked_runtime_disclosure_keeps_phase_one_pending_for_finalization() -> None:
    result = {
        "conversation_decision": {
            "requires_host_model": True,
            "state_emoticon": "🌿",
            "timestamp_contract": {
                "trusted": True,
                "timezone": "Europe/Warsaw",
                "sample_iso": "2026-08-28T12:00:00+02:00",
                "source": "deterministic_test_clock",
            },
        },
        "runtime_turn_contract": {"requires_host_model": True},
        "final_response_contract": {
            "requires_host_model": True,
            "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": "2026-08-28T12:00:00+02:00",
            "timestamp_source": "deterministic_test_clock",
            "timestamp_trusted": True,
            "author_id": "latka",
            "author_label": "Łatka",
            "author_source": "identity_canon",
            "state_emoticon": "🌿",
        },
        "trace": {
            "turn_id": "turn-v16323",
            "trace_id": "trace-v16323",
            "timestamp_header": HEADER,
        },
        "runtime_truth_gate": {
            "normal_response_allowed": False,
            "errors": ["model_guided_speech_required"],
        },
        "final_visible_text": "Host generation is required before a visible reply.",
    }

    pending, missing = _host_finalization_pending(result, can_continue=True)

    assert pending is True
    assert missing == []


def test_valid_grounded_recall_is_correlated_and_legally_visible() -> None:
    result = run_host_pre_response_gate(
        "Przypomnij sobie bursztynowy kompas.",
        invoke_runtime=lambda _text: _memory_response(),
        requested_runtime_root="/runtime_A",
    )

    assert result["ok"] is True
    assert result["visible_text"] == MEMORY_TEXT
    assert result["visible_output_source"] == "runtime_exact"
    observability = result["memory_recall_observability"]
    assert observability["memory_recall_status"] == "valid_grounded_recall"
    assert observability["runtime_turn_id"] == result["host_pre_response_gate"]["runtime_turn_id"]
    assert observability["trace_id"] == result["host_pre_response_gate"]["trace_id"]
    assert observability["requested_runtime_root"] == "/runtime_A"
    assert observability["resolved_active_root"] == "/runtime_B"
    assert observability["daemon_endpoint_root"] == "/runtime_B"
    assert observability["daemon_identity_verified"] is True


class _CountingJaznRuntimeSession(JaznRuntimeSession):
    created = 0
    exact_user_texts: list[str] = []

    def __init__(self, config: JaznConfig, **kwargs: Any) -> None:
        type(self).created += 1
        super().__init__(config, **kwargs)

    def process_user_text(self, user_text: str, **kwargs: Any) -> dict[str, Any]:
        type(self).exact_user_texts.append(user_text)
        return super().process_user_text(user_text, **kwargs)


def _runtime_root(path: Path) -> Path:
    root = path.resolve()
    package = root / "latka_jazn"
    package.mkdir(parents=True)
    (package / "version.py").write_text('PACKAGE_VERSION = "test"\n', encoding="utf-8")
    (root / "run.py").write_text("", encoding="utf-8")
    return root


def _install_synthetic_active_memory(subject_root: Path) -> tuple[Path, str]:
    database = resolve_memory_tier_database_path(subject_root)
    database.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "Syntetyczny zapis pamięci: bursztynowy kompas; "
        "spaceru nad rzeką."
    )
    evidence = (
        SourceEvidence(
            source_type="synthetic_issue_180_fixture",
            source_id="issue-180:turn-source",
            source_sha256=hashlib.sha256(b"issue-180:turn-source").hexdigest(),
        ),
    )
    now = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
    memory_id = deterministic_memory_id(
        tier=MemoryTier.WORKING,
        kind=MemoryKind.CONVERSATION_CONTEXT,
        content=content,
        domain="synthetic_issue_180",
        mode="deterministic_e2e",
        evidence=evidence,
    )
    record = WorkingMemoryRecord(
        memory_id=memory_id,
        tier=MemoryTier.WORKING,
        kind=MemoryKind.CONVERSATION_CONTEXT,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        domain="synthetic_issue_180",
        mode="deterministic_e2e",
        truth_status=MemoryTruthStatus.SOURCE_RECORDED,
        confidence=0.97,
        importance=0.91,
        created_at_utc=now,
        updated_at_utc=now,
        evidence=evidence,
        session_id="session-v16323-e2e",
        turn_id="synthetic-source-turn",
    )
    with MemoryTierStore(database) as store:
        summary = store.save_record(record)
    assert summary.records_written == 1
    assert summary.evidence_written == 1
    return database, content


def _bind_transport(
    result: dict[str, Any],
    transport: dict[str, Any],
) -> dict[str, Any]:
    bound = dict(result)
    bound["transport_observability"] = dict(transport)
    bound["host_pre_response_gate_context"] = {
        "runtime_turn_invoked": True,
        "requested_runtime_root": transport["requested_runtime_root"],
    }
    bound["chatgpt_host_presentation"] = build_chatgpt_host_presentation_packet(bound)
    return bound


def test_two_turn_persistent_subject_b_executes_grounded_active_memory_recall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {
        "JAZN_TEST_MODE": "1",
        "JAZN_MODEL_ADAPTER": "null",
        "JAZN_ALLOW_NETWORK": "0",
        "JAZN_DICTIONARY_ALLOW_NETWORK": "0",
        "JAZN_NETWORK_TIME_FIRST": "0",
        "JAZN_NETWORK_TIME_IN_TURN": "0",
        "JAZN_REST_CYCLE_ENABLED": "0",
        "JAZN_MEMORY_SYNC_MODE": "off",
        "JAZN_HARD_WORKER_PROCESS_ISOLATION": "0",
    }.items():
        monkeypatch.setenv(name, value)

    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    database, synthetic_content = _install_synthetic_active_memory(subject_root)
    second_text = "Przypomnij sobie bursztynowy kompas ze spaceru nad rzeką."
    preflight_plan = MemorySearchPlanner(subject_root).plan(second_text)
    preflight_recall = LivingMemoryGateway(
        subject_root,
        discovery_cache_seconds=0.0,
    ).search(preflight_plan)
    assert any(
        synthetic_content == str(hit.get("content_excerpt") or "")
        for hit in (preflight_recall.get("hits") or [])
        if isinstance(hit, dict)
    ), {
        "status": preflight_recall.get("status"),
        "counts": preflight_recall.get("counts"),
        "issues": preflight_recall.get("issues"),
        "sources": preflight_recall.get("sources"),
    }
    config_b = JaznConfig(root=subject_root)
    _CountingJaznRuntimeSession.created = 0
    _CountingJaznRuntimeSession.exact_user_texts = []

    monkeypatch.setattr(
        runtime_daemon,
        "verify_package_integrity_manifest",
        lambda root: {"ok": Path(root).resolve() == subject_root, "errors": []},
    )
    monkeypatch.setattr(
        runtime_daemon,
        "read_source_provenance",
        lambda root, **_kwargs: SimpleNamespace(
            to_dict=lambda: {
                "status": (
                    "verified_export_without_git_history"
                    if Path(root).resolve() == subject_root
                    else "unverified"
                ),
                "limitations": ["synthetic issue #180 E2E root"],
            }
        ),
    )
    monkeypatch.setattr(
        daemon_autostart,
        "start_daemon",
        lambda *_args, **_kwargs: pytest.fail("healthy subject B must be reused"),
    )

    server = runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=config_b,
        marker_path=active_runtime_marker_path(subject_root),
        session_factory=_CountingJaznRuntimeSession,
        execution_timeout_seconds=90.0,
        hard_worker_process_isolation=False,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        subject_marker = server.write_marker()
        assert Path(str(subject_marker["active_root"])).resolve() == subject_root
        requested_marker_path = active_runtime_marker_path(requested_root)
        requested_marker_path.parent.mkdir(parents=True, exist_ok=True)
        requested_marker_path.write_text(
            json.dumps(subject_marker, ensure_ascii=False),
            encoding="utf-8",
        )

        status_before = runtime_daemon.status_daemon(
            JaznConfig(root=requested_root),
            host="127.0.0.1",
            port=port,
        )
        assert status_before["active_state"] == "active_trusted"
        assert status_before["requested_runtime_root"] == str(requested_root)
        assert status_before["resolved_active_root"] == str(subject_root)
        assert status_before["endpoint_reported_active_root"] == str(subject_root)
        assert status_before["endpoint_identity_matches"] is True

        ensured = daemon_autostart.ensure_daemon_for_runtime_turn(
            JaznConfig(root=requested_root),
            command="--chat-gpt",
            host="127.0.0.1",
            port=port,
            env={},
        )
        transport = ensured.transport_observability()
        assert ensured.ok is True
        assert transport["selected_transport"] == "persistent_daemon"
        assert transport["fallback_reason"] == "daemon_reused"
        assert transport["requested_runtime_root"] == str(requested_root)
        assert transport["resolved_active_root"] == str(subject_root)
        assert transport["daemon_endpoint_root"] == str(subject_root)
        assert transport["daemon_identity_verified"] is True
        assert transport["one_shot_verified"] is False

        first_text = "Hej."
        first_raw = runtime_daemon.chat_daemon(
            config_b,
            first_text,
            host="127.0.0.1",
            port=port,
            session_id="session-v16323-e2e",
            request_id="trace-v16323-first",
            timeout=90.0,
            poll_interval=0.02,
        )
        if first_raw.get("ok") is not True:
            pytest.fail(
                json.dumps(
                    {
                        "error_code": first_raw.get("error_code"),
                        "execution_state": first_raw.get("execution_state"),
                        "answer_ok": first_raw.get("answer_ok"),
                        "host_finalization_pending": first_raw.get("host_finalization_pending"),
                        "host_finalization_contract_missing": first_raw.get("host_finalization_contract_missing"),
                        "runtime_truth_gate": first_raw.get("runtime_truth_gate"),
                        "final_visible_integrity": first_raw.get("final_visible_integrity"),
                        "chatgpt_host_bridge": first_raw.get("chatgpt_host_bridge"),
                        "conversation_decision": first_raw.get("conversation_decision"),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        first = _bind_transport(first_raw, transport)
        first_job = server.get_chat_job("trace-v16323-first")
        assert first_job is not None

        class _LifecycleGateway:
            def __init__(self, expected_job: runtime_daemon.DaemonChatJob) -> None:
                self.expected_job = expected_job

            def note_host_finalization(
                self,
                pending: dict[str, Any],
                *,
                outcome: str,
                reason: str,
                terminal: bool = False,
            ) -> dict[str, Any]:
                binding = pending["binding"]
                target, error = server.note_host_finalization(
                    request_id=str(binding["daemon_request_id"]),
                    turn_id=str(binding["turn_id"]),
                    trace_id=str(binding["trace_id"]),
                    request_contract_hash=str(pending["request_contract_hash"]),
                    outcome=outcome,
                    reason=reason,
                    terminal=terminal,
                )
                assert error is None and target is self.expected_job
                assert target is not None
                return target.snapshot(include_result=False)

        def finalize_first(candidate: str, presentation: dict[str, Any]) -> dict[str, Any]:
            bridge = presentation["chatgpt_host_bridge"]
            issued = issue_continuation_token(
                subject_root,
                turn_id=str(bridge["turn_id"]),
                request_contract_hash=str(bridge["host_request_contract_hash"]),
            )
            finalized = jazn_finalize_reply.run(
                root=subject_root,
                continuation_token=str(issued["continuation_token"]),
                final_text=candidate,
                final_text_sha256=sha256_host_visible_text(candidate),
                lifecycle_gateway=_LifecycleGateway(first_job),
            )
            assert finalized["isError"] is False, finalized
            return dict(finalized["structuredContent"])

        first_visible = run_host_pre_response_gate(
            first_text,
            invoke_runtime=lambda exact: first if exact == first_text else {},
            generate_host_candidate=lambda _presentation: "Cieszę się, że jesteś. Jestem gotowa na tę rozmowę.",
            finalize_runtime_candidate=finalize_first,
            requested_runtime_root=requested_root,
        )
        assert first_visible["ok"] is True
        assert first_visible["visible_output_source"] in {"runtime_exact", "runtime_finalized"}
        assert first_visible["visible_output_source"] != "host_diagnostic"
        assert first_job.status == "completed"
        assert thread.is_alive()
        assert server.shutdown_requested.is_set() is False

        recall_after_first = LivingMemoryGateway(
            subject_root,
            discovery_cache_seconds=0.0,
        ).search(preflight_plan)
        assert any(
            synthetic_content == str(hit.get("content_excerpt") or "")
            for hit in (recall_after_first.get("hits") or [])
            if isinstance(hit, dict)
        ), {
            "status": recall_after_first.get("status"),
            "counts": recall_after_first.get("counts"),
            "issues": recall_after_first.get("issues"),
        }
        second_raw = runtime_daemon.chat_daemon(
            config_b,
            second_text,
            host="127.0.0.1",
            port=port,
            session_id="session-v16323-e2e",
            request_id="trace-v16323-second",
            timeout=90.0,
            poll_interval=0.02,
        )
        second = _bind_transport(second_raw, transport)
        second_job = server.get_chat_job("trace-v16323-second")
        assert second_job is not None
        second_presentation = second["chatgpt_host_presentation"]
        second_bridge = second_presentation["chatgpt_host_bridge"]
        second_host_context = second_bridge["host_generation_context"]
        used_memory_item_ids = list(second_host_context.get("allowed_memory_item_ids") or [])
        second_model_context = second_host_context.get("model_context") or {}
        allowed_memory_items = list(second_model_context.get("allowed_memory_items") or [])
        if not used_memory_item_ids:
            recall_contract = second.get("memory_recall_contract") or {}
            recall_items = list(recall_contract.get("items") or [])
            pytest.fail(
                json.dumps(
                    {
                        "memory_recall_observability": second.get("memory_recall_observability"),
                        "memory_recall_contract_item_count": len(recall_items),
                        "memory_recall_contract_first_item": recall_items[:1],
                        "host_allowed_memory_item_count": len(allowed_memory_items),
                        "host_allowed_memory_item_ids": used_memory_item_ids,
                        "presentation_action": second_presentation.get("action"),
                        "presentation_diagnostic_reason": second_presentation.get(
                            "diagnostic_reason"
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        recall_items = list((second.get("memory_recall_contract") or {}).get("items") or [])
        assert synthetic_content in str(recall_items)
        assert synthetic_content in str(allowed_memory_items)
        assert set(used_memory_item_ids) == {
            str(item.get("item_id") or "")
            for item in allowed_memory_items
            if isinstance(item, dict)
        }

        def finalize_second(candidate: str, presentation: dict[str, Any]) -> dict[str, Any]:
            bridge = presentation["chatgpt_host_bridge"]
            issued = issue_continuation_token(
                subject_root,
                turn_id=str(bridge["turn_id"]),
                request_contract_hash=str(bridge["host_request_contract_hash"]),
            )
            finalized = jazn_finalize_reply.run(
                root=subject_root,
                continuation_token=str(issued["continuation_token"]),
                final_text=candidate,
                final_text_sha256=sha256_host_visible_text(candidate),
                used_memory_item_ids=used_memory_item_ids,
                lifecycle_gateway=_LifecycleGateway(second_job),
            )
            assert finalized["isError"] is False, finalized
            return dict(finalized["structuredContent"])

        second_visible = run_host_pre_response_gate(
            second_text,
            invoke_runtime=lambda exact: second if exact == second_text else {},
            generate_host_candidate=lambda _presentation: (
                "Pamiętam syntetyczny ślad o bursztynowym kompasie i spacerze nad rzeką; "
                "źródłem jest aktywna pamięć tej tury testowej."
            ),
            finalize_runtime_candidate=finalize_second,
            requested_runtime_root=requested_root,
        )

        assert second_visible["ok"] is True, second_visible
        assert second_visible["visible_output_source"] in {"runtime_exact", "runtime_finalized"}
        assert second_visible["visible_output_source"] != "host_diagnostic"
        memory = second_visible["memory_recall_observability"]
        assert memory["memory_recall_requested"] is True
        assert memory["memory_recall_executed"] is True
        assert memory["memory_search_ready"] is True
        assert memory["memory_recall_status"] == "valid_grounded_recall"
        assert memory["memory_source_count"] >= 1
        assert memory["memory_provenance_available"] is True
        assert "active_memory" in memory["memory_source_types"]
        assert memory["runtime_turn_id"] == second["chatgpt_host_presentation"]["turn_id"]
        assert memory["trace_id"] == second["chatgpt_host_presentation"]["trace_id"]
        assert memory["selected_transport"] == "persistent_daemon"
        assert memory["fallback_reason"] == "daemon_reused"
        assert memory["requested_runtime_root"] == str(requested_root)
        assert memory["resolved_active_root"] == str(subject_root)
        assert memory["daemon_endpoint_root"] == str(subject_root)
        assert memory["daemon_identity_verified"] is True
        assert second_text not in repr(memory)

        first_trace = first["trace"]
        second_trace = second["trace"]
        assert first_trace["turn_id"] != second_trace["turn_id"]
        assert first_trace["trace_id"] == "trace-v16323-first"
        assert second_trace["trace_id"] == "trace-v16323-second"
        assert first["chatgpt_host_presentation"]["turn_id"] == first_trace["turn_id"]
        assert second["chatgpt_host_presentation"]["turn_id"] == second_trace["turn_id"]
        assert first["chatgpt_host_presentation"]["trace_id"] == first_trace["trace_id"]
        assert second["chatgpt_host_presentation"]["trace_id"] == second_trace["trace_id"]
        assert _CountingJaznRuntimeSession.created == 1
        assert _CountingJaznRuntimeSession.exact_user_texts == [first_text, second_text]
        assert len(server.sessions) == 1
        assert server.state.turn_count == 2
        assert database.is_file()

        status_after = runtime_daemon.status_daemon(
            JaznConfig(root=requested_root),
            host="127.0.0.1",
            port=port,
        )
        assert status_after["active_state"] == "active_trusted"
        assert status_after["endpoint_identity_matches"] is True
        assert status_after["resolved_active_root"] == str(subject_root)
    finally:
        server.shutdown()
        server.close_sessions()
        server.server_close()
        thread.join(timeout=5.0)
