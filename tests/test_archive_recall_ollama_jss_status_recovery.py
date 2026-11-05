"""Regression: preserve recall provenance while repairing preview and JSS states."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from latka_jazn.core.archive_recall_policy import filter_verified_archive_hits
from latka_jazn.core.model_guided_speech_runtime import _command_from_client_context
from latka_jazn.version import PACKAGE_VERSION_FULL
from tools.jazn_run_studio.core import daemon_evidence
from tools.jazn_run_studio.service_visual_state import visual_state


def _hit(confidence: float, *, excerpt: str = "archiwalny tekst", review: str = "unreviewed") -> dict:
    return {
        "identity_confidence": confidence,
        "review_status": review,
        "excerpt": excerpt,
        "message_uid": "synthetic-uid",
        "role": "assistant",
    }


def test_archive_identity_threshold_is_not_relaxed() -> None:
    accepted, audit = filter_verified_archive_hits(
        [_hit(0.45), _hit(0.49), _hit(0.85, review="rejected"), _hit(0.99, excerpt="")],
        limit=5,
    )
    assert accepted == []
    assert audit["returned"] == 4
    assert audit["rejected_identity"] == 2
    assert audit["rejected_review"] == 1
    assert audit["rejected_empty_excerpt"] == 1
    assert audit["identity_review_required"] is True


def test_archive_accepts_later_verified_hits_after_low_confidence_candidates() -> None:
    raw = [_hit(0.45) for _ in range(10)] + [_hit(0.85), _hit(0.92)]
    accepted, audit = filter_verified_archive_hits(raw, limit=2)
    assert len(accepted) == 2
    assert audit["returned"] == 12
    assert audit["rejected_identity"] == 10
    assert audit["eligible"] == 2


@pytest.mark.parametrize("bad", ["not-a-number", float("nan"), float("inf"), -1, 0.0])
def test_archive_invalid_identity_values_fail_closed(bad) -> None:
    accepted, audit = filter_verified_archive_hits([_hit(bad)], limit=3)
    assert not accepted
    assert audit["identity_review_required"] is True


def test_runtime_archive_overfetch_keeps_later_verified_hit(monkeypatch, tmp_path) -> None:
    from latka_jazn.core import engine as engine_module

    requests = []

    class FakeStore:
        def __init__(self, root):
            assert root == tmp_path

        def search(self, query, **options):
            requests.append((query, options))
            raw = [_hit(0.45) for _ in range(6)] + [_hit(0.90)]
            for hit in raw:
                hit.update({
                    "title": "fixture", "source_name": "fixture",
                    "content_hash": "synthetic-hash",
                })
            return SimpleNamespace(to_dict=lambda: {
                "status": "ok", "candidate_count": 7, "hits": raw,
                "issues": [],
            })

    monkeypatch.setattr(engine_module, "ConversationArchiveStore", FakeStore)
    from typing import cast
    # Deliberately avoid starting a daemon or constructing an engine.
    instance = cast(
        engine_module.JaznEngine,
        SimpleNamespace(config=SimpleNamespace(root=tmp_path)),
    )
    hits, report = engine_module.JaznEngine._conversation_archive_context_hits(
        instance, ["sieć", "snów"], limit=2,
    )
    assert requests[0][1]["limit"] >= 7
    assert requests[0][1]["include_snippets"] is True
    assert len(hits) == 1
    assert report["eligibility"]["rejected_identity"] == 6
    assert report["eligibility"]["eligible"] == 1


def test_explicit_local_preview_is_not_routed_as_chatgpt_host() -> None:
    from main import _build_parser

    args = _build_parser().parse_args(
        ["--dev-preview", "--preview-local-ollama", "Przypomnij rozmowę"]
    )
    assert args.dev_preview is True
    assert args.preview_local_ollama is True
    assert _command_from_client_context({
        "client": "ollama_dev_preview",
        "command": "--chat-ollama",
        "language_channel": "ollama",
    }) == "--chat-ollama"
    assert _command_from_client_context({"client": "chatgpt_dev_preview"}) == "--chat-gpt"


def test_jss_optional_services_do_not_turn_red_when_unconfigured() -> None:
    assert visual_state("cloudflare", {"ready": False}) == "unknown"
    assert visual_state("cloudflare", {"ready": True}) == "reachable"
    assert visual_state("memory", {"ready": False}) == "unknown"
    assert visual_state("memory", {"memory_search_ready": True,
                                    "continuity_ready": False}) == "reachable"
    assert visual_state("supervisor", {"ready": False, "active": False}) == "stopped"
    assert visual_state("gateway", {"ready": False}) == "unknown"
    assert visual_state("ollama", {"ready": False, "endpoint_reachable": True}) == "reachable"
    assert visual_state("ollama", {"endpoint_reachable": True,
                                   "selected_model_present": True,
                                   "generation_verified": True}) == "ready"
    assert visual_state("cloudflare", {"status": "error"}) == "error"


def test_jss_verified_live_daemon_does_not_use_historical_marker(tmp_path) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text(
        f"PACKAGE_VERSION={PACKAGE_VERSION_FULL!r}\n", encoding="utf-8")
    record = {
        "resolved_active_root": str(tmp_path),
        "runtime_version_full": PACKAGE_VERSION_FULL,
        "runtime_core_ready": True,
        "operational_state": "active_ready",
        "daemon": {
            "runtime_version_full": PACKAGE_VERSION_FULL,
            "readiness_state": "ready",
            "active_state": "active_trusted",
            "endpoint_reachable": True,
            "process_identity_confirmed": True,
            "endpoint_identity_matches": True,
            "endpoint_heartbeat_fresh": True,
            "marker": {"runtime_version_full": "older-marker-version"},
        },
    }
    evidence = daemon_evidence(record, expected_root=tmp_path)
    assert evidence["version_matches"] is True
    assert evidence["root_matches"] is True
    assert evidence["conversation_ready"] is True
    assert visual_state("runtime", evidence) == "ready"

    record["daemon"]["ping"] = {"runtime_version": "other-live-version"}
    mismatch = daemon_evidence(record, expected_root=tmp_path)
    assert mismatch["version_matches"] is False
    assert visual_state("runtime", mismatch) == "error"


def test_jss_optional_not_ready_probe_does_not_turn_service_popup_red(monkeypatch) -> None:
    import os
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QWidget
    from tools.jazn_run_studio.service_status_dialog import ServiceStatusDialog

    app = QApplication.instance() or QApplication([])
    assert app is not None
    host = QWidget()
    dialog = ServiceStatusDialog(host, lambda: None)
    dialog.observe("probe:gateway", "probe", {
        "service": "gateway", "ready": False, "endpoint_reachable": False,
    })
    dialog.observe("probe:gateway", "state", {
        "state": "failed", "error": "service_not_ready",
    })
    assert "Niezweryfikowany" in dialog.indicators["mcp"][1].text()
    dialog.observe("probe:gateway", "state", {
        "state": "failed", "error": "connection_refused_unexpected",
    })
    assert "Błąd" in dialog.indicators["mcp"][1].text()
    dialog.close()
    host.close()


def test_jss_memory_evidence_preserves_partial_readiness() -> None:
    from tools.jazn_run_studio.core import memory_evidence
    reported = memory_evidence({
        "capability_readiness": {
            "memory_search_ready": True,
            "full_autobiographical_recall_ready": False,
            "continuity_ready": False,
        },
        "startup": {"memory_continuity_status": {
            "normalization_status": "normalization_stale",
            "wake_state_status": "normalization_stale",
        }},
    })
    assert reported["service"] == "memory"
    assert reported["ready"] is False
    assert reported["memory_search_ready"] is True
    assert reported["normalization_status"] == "normalization_stale"
    assert visual_state("memory", reported) == "reachable"
    assert visual_state("runtime", reported) != "ready"
