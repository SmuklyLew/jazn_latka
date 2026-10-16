from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from latka_jazn.core import turn_settlement as subject
from latka_jazn.core.chatgpt_host_pending_store import HostRequestStoreError

REQUEST_ID = "request-stable-1"
TURN_ID = "turn-stable-1"
TRACE_ID = "trace-stable-1"
TEXT = "Jedna wiadomość użytkownika"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fake_lifecycle(*, state: str = "pending", bound_text: str = TEXT,
                    notification: str = "pending") -> dict[str, object]:
    return {
        "found": True,
        "state": state,
        "request_contract_hash": "a" * 64,
        "binding": {
            "daemon_request_id": REQUEST_ID,
            "turn_id": TURN_ID,
            "trace_id": TRACE_ID,
            "user_text_sha256": _sha(bound_text),
        },
        "generation_context": {},
        "daemon_finalization_notification_state": notification,
    }


def _resolve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *,
             state: str = "pending", bound_text: str = TEXT,
             expected_text: str | None = None,
             supplied_hash: str | None = None,
             notification: str = "pending") -> dict[str, object]:
    monkeypatch.setattr(
        subject, "host_request_lifecycle_by_daemon_request_id",
        lambda *_args, **_kwargs: _fake_lifecycle(
            state=state, bound_text=bound_text, notification=notification
        ),
    )
    return subject.resolve_durable_turn_settlement(
        tmp_path, daemon_request_id=REQUEST_ID,
        expected_user_text=expected_text,
        expected_user_text_sha256=supplied_hash,
    )


def test_matching_user_text_and_sha_allow_pending_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    result = _resolve(monkeypatch, tmp_path, expected_text=TEXT, supplied_hash=_sha(TEXT))
    assert result["valid"] is True
    assert result["settlement_state"] == "awaiting_host_finalization"


@pytest.mark.parametrize("supplied_hash", ["garbage", "", "1" * 63, "not-a-sha"])
def test_explicit_invalid_expected_digest_fails_closed_without_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, supplied_hash: str,
) -> None:
    result = _resolve(monkeypatch, tmp_path, supplied_hash=supplied_hash)
    assert result["valid"] is False
    assert "invalid_expected_user_text_sha256" in result["violations"]


def test_conflicting_expected_text_and_hash_cannot_bypass_binding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    result = _resolve(monkeypatch, tmp_path, expected_text=TEXT, supplied_hash=_sha("INNY"))
    assert result["valid"] is False
    assert "expected_user_text_evidence_conflict" in result["violations"]


def test_missing_or_wrong_bound_message_digest_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    result = _resolve(monkeypatch, tmp_path, expected_text=TEXT, bound_text="inny tekst")
    assert result["valid"] is False
    assert "user_text_binding_mismatch" in result["violations"]


def test_consumed_without_verified_final_capture_never_claims_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        subject, "read_committed_host_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HostRequestStoreError("committed_host_request_capture_unavailable")
        ),
    )
    result = _resolve(monkeypatch, tmp_path, state="consumed", expected_text=TEXT)
    assert result["valid"] is False
    assert any(item.startswith("committed_final_invalid:")
               for item in result["violations"])


@pytest.mark.parametrize(
    ("notification", "confirmed", "pending"),
    [("delivered", True, False), ("pending", False, True),
     ("pending_retry", False, True)],
)
def test_accepted_capture_and_daemon_notification_have_distinct_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    notification: str, confirmed: bool, pending: bool,
) -> None:
    monkeypatch.setattr(subject, "read_committed_host_request",
                        lambda *_args, **_kwargs: {"state": "consumed"})
    result = _resolve(monkeypatch, tmp_path, state="consumed",
                      expected_text=TEXT, notification=notification)
    assert result["valid"] is True
    assert result["settlement_state"] == "accepted_final_committed"
    assert result["daemon_projection_confirmed"] is confirmed
    assert result["daemon_projection_pending"] is pending
