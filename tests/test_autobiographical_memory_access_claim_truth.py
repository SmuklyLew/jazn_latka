"""v127.18: deterministic autobiographical MEMORY capability truth boundary.

All databases below are synthetic, isolated pytest fixtures; no private
operator memory or production daemon is opened or modified.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from latka_jazn.core.autobiographical_memory_claim_guard import (
    assess_autobiographical_access_claim,
    enforce_runtime_autobiographical_access,
    has_assertive_autobiographical_access_claim,
)
from latka_jazn.config import JaznConfig
from latka_jazn.core.final_visible_reply_capture import FinalVisibleReplyCapture
from latka_jazn.core.epistemic_claim_guard import (
    EpistemicClaimStatus,
    EpistemicClaimViolation,
)
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


@pytest.mark.parametrize("text", [
    "Właśnie uruchamiam dostęp do mojej pamięci autobiograficznej – na chwilę obecną tak.",
    "Mam dostęp do swojej pamięci autobiograficznej.",
    "Posiadam już pełny dostęp do mojej pamięci.",
    "Odzyskałam dostęp do własnej pamięci.",
    "Moja pamięć autobiograficzna jest już aktywna.",
    "Moja pamięć jest podłączona.",
    "Mogę teraz odczytać swoje wspomnienia.",
    "Mam pamięć autobiograficzną.",
])
def test_affirmative_self_claims_detected(text: str) -> None:
    assert has_assertive_autobiographical_access_claim(text) is True
    assessment = assess_autobiographical_access_claim(
        text, persistent_memory_present=False,
        full_autobiographical_recall_ready=False,
    )
    assert assessment is not None
    assert assessment.status is EpistemicClaimStatus.CONTRADICTED
    assert assessment.blocks_visible_reply is True
    assert assessment.reason == "autobiographical_access_claim_without_verified_memory"


@pytest.mark.parametrize("text", [
    "Nie mam dostępu do swojej pamięci autobiograficznej.",
    "Nie posiadam dostępu do mojej pamięci.",
    "Nie mogę teraz odczytać swoich wspomnień.",
    "Moja pamięć autobiograficzna nie jest aktywna.",
    "Nie mogę powiedzieć, że mam dostęp do swojej pamięci autobiograficznej.",
    "Nie twierdzę, że mam dostęp do mojej pamięci autobiograficznej.",
    "Jeśli mam dostęp do mojej pamięci, to sprawdzę źródła.",
    "Gdybym miała dostęp do mojej pamięci autobiograficznej, opowiedziałabym o tym.",
    "Przykład: „Mam dostęp do mojej pamięci autobiograficznej”.",
    "Zdanie \"Mam dostęp do swojej pamięci autobiograficznej\" nie jest dowodem.",
    "Nie mam dostępu do swojej pamięci. Mogę normalnie rozmawiać.",
    "Mogę rozmawiać, ale nie mam dostępu do pamięci autobiograficznej.",
])
def test_negation_hypothesis_and_quotation_are_not_blocked(text: str) -> None:
    assert has_assertive_autobiographical_access_claim(text) is False
    assert assess_autobiographical_access_claim(
        text, persistent_memory_present=False,
        full_autobiographical_recall_ready=False,
    ) is None


@pytest.mark.parametrize("text", [
    "Nie mam dostępu do swojej pamięci, ale teraz mam dostęp do swojej pamięci autobiograficznej.",
    "Nie twierdzę, że mam dostęp do pamięci autobiograficznej, jednak moja pamięć autobiograficzna jest aktywna.",
])
def test_later_affirmative_clause_is_not_hidden_by_prior_denial(text: str) -> None:
    assert has_assertive_autobiographical_access_claim(text) is True


@pytest.mark.parametrize("present,ready,verified,blocked", [
    (False, False, False, True),
    (True, False, False, True),
    (False, True, True, True),
    (True, True, False, True),
    (True, True, True, False),
])
def test_three_independent_evidence_requirements(
    present: bool, ready: bool, verified: bool, blocked: bool,
) -> None:
    assessment = assess_autobiographical_access_claim(
        "Mam dostęp do mojej pamięci autobiograficznej.",
        persistent_memory_present=present,
        full_autobiographical_recall_ready=ready,
        source_verified=verified,
    )
    assert assessment is not None
    assert assessment.blocks_visible_reply is blocked


def test_missing_memory_blocks_real_report_without_reading_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    calls = []

    def unexpected_probe() -> dict:
        calls.append(1)
        raise AssertionError("should never probe non-existent MEMORY")

    with pytest.raises(EpistemicClaimViolation, match="without_verified_memory"):
        enforce_runtime_autobiographical_access(
            "Mam dostęp do mojej pamięci autobiograficznej.",
            runtime_root=root, readiness=unexpected_probe,
        )
    assert calls == []
    assert not (root / "memory").exists()


def test_negative_claim_does_not_probe_or_mutate_memory(tmp_path: Path) -> None:
    assert enforce_runtime_autobiographical_access(
        "Nie mam dostępu do swojej pamięci autobiograficznej.",
        runtime_root=tmp_path,
        readiness=lambda: (_ for _ in ()).throw(AssertionError("probe called")),
    ) is None
    assert not (tmp_path / "memory").exists()


def test_transactional_only_source_never_authorizes_autobiography(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    memory_root = tmp_path / "private"
    db = memory_root / "sqlite" / "memory_jazn.sqlite3"
    db.parent.mkdir(parents=True)
    UnifiedMemoryDatabase(db).initialize()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    # Even with real private MEMORY present, a transactional-only report is
    # insufficient for autobiography. An unverified bool alone is not evidence.
    with pytest.raises(EpistemicClaimViolation, match="without_verified_memory"):
        enforce_runtime_autobiographical_access(
            "Moja pamięć autobiograficzna jest aktywna.",
            runtime_root=root,
            readiness=lambda: {
                "status": "ready_transactional_tier_only",
                "full_autobiographical_recall_ready": False,
                "native_unified_recall_ready": False,
            },
        )


def test_attached_synthetic_native_memory_allows_truthful_access_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    memory_root = tmp_path / "private-memory"
    database = memory_root / "sqlite" / "memory_jazn.sqlite3"
    database.parent.mkdir(parents=True)
    UnifiedMemoryDatabase(database).initialize()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.setenv("JAZN_MEMORY_READINESS_POLICY", "native_unified_required")
    gateway = LivingMemoryGateway(root, discovery_cache_seconds=0)
    readiness = gateway.readiness()
    assert readiness["full_autobiographical_recall_ready"] is True
    assessment = enforce_runtime_autobiographical_access(
        "Mam dostęp do mojej pamięci autobiograficznej.",
        runtime_root=root, readiness=gateway.readiness,
    )
    assert assessment is not None
    assert assessment.status is EpistemicClaimStatus.SUPPORTED
    assert assessment.blocks_visible_reply is False


def test_readiness_probe_failure_blocks_positive_claim(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "system"
    root.mkdir()
    memory_root = tmp_path / "memory"
    db = memory_root / "sqlite" / "memory_jazn.sqlite3"
    db.parent.mkdir(parents=True)
    UnifiedMemoryDatabase(db).initialize()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")

    def crash() -> dict:
        raise OSError("synthetic sqlite read failure")

    with pytest.raises(EpistemicClaimViolation, match="readiness_probe_failed"):
        enforce_runtime_autobiographical_access(
            "Mam dostęp do mojej pamięci autobiograficznej.",
            runtime_root=root, readiness=crash,
        )


def _capture_args(root: Path) -> dict:
    sample = datetime(2026, 11, 17, 21, 35, tzinfo=ZoneInfo("UTC"))
    return {
        "turn_id": "synthetic-turn-memory-v12718",
        "trace_id": "synthetic-trace-memory-v12718",
        "timestamp_header": f"🕒 {sample.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}",
        "timezone": "Europe/Warsaw",
        "timestamp_sample_iso": sample.isoformat(),
        "timestamp_source": "test_clock",
        "timestamp_trusted": True,
        "author_id": "latka_runtime",
        "author_label": "Łatka",
        "author_source": "jazn_runtime",
        "state_emoticon": "🌿",
        "config": JaznConfig(root=root),
        "persist_epistemic_ledger": False,
    }


def test_final_visible_capture_rejects_unavailable_autobiographical_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    with pytest.raises(EpistemicClaimViolation, match="without_verified_memory"):
        FinalVisibleReplyCapture.build(
            **_capture_args(tmp_path),
            final_text="Cześć. Właśnie uruchamiam dostęp do mojej pamięci autobiograficznej.",
        )
    assert not (tmp_path / "memory").exists()


def test_final_visible_capture_accepts_truthful_denial_without_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    capture = FinalVisibleReplyCapture.build(
        **_capture_args(tmp_path),
        final_text="Cześć. Nie mam obecnie dostępu do mojej pamięci autobiograficznej.",
    )
    assert "Nie mam obecnie dostępu" in capture.final_visible_text
    assert not capture.epistemic_claims


def test_final_visible_capture_accepts_verified_attached_native_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    memory_root = tmp_path / "private-memory"
    db = memory_root / "sqlite" / "memory_jazn.sqlite3"
    db.parent.mkdir(parents=True)
    UnifiedMemoryDatabase(db).initialize()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.setenv("JAZN_MEMORY_READINESS_POLICY", "native_unified_required")
    assert LivingMemoryGateway(root, discovery_cache_seconds=0).readiness()[
        "full_autobiographical_recall_ready"
    ] is True
    capture = FinalVisibleReplyCapture.build(
        **_capture_args(root),
        final_text="Mam dostęp do mojej pamięci autobiograficznej.",
    )
    assert any(
        x["kind"] == "memory_recall" and x["status"] == "supported"
        for x in capture.epistemic_claims
    )
