from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from latka_jazn.core.message_envelope import (
    MessageEnvelope,
    TIMESTAMP_HEADER_RE,
    normalize_newlines,
)
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("host_visible_finalization", version=PACKAGE_VERSION_FULL)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonicalize_host_visible_text(text: str) -> str:
    """Canonical host text representation: UTF-8 text with LF newlines and no BOM."""
    return normalize_newlines(str(text or "")).lstrip("\ufeff")


def sha256_host_visible_text(text: str) -> str:
    return hashlib.sha256(canonicalize_host_visible_text(text).encode("utf-8")).hexdigest()


def _sha_text(text: str) -> str:
    return sha256_host_visible_text(text)


@dataclass(slots=True, frozen=True)
class HostVisibleFinalizationViolation:
    code: str
    message: str
    repairable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class HostVisibleFinalizationPolicy:
    max_utf8_bytes: int = 2 * 1024 * 1024
    render_body_when_envelope_missing: bool = True
    require_supplied_text_hash: bool = True
    reject_foreign_timestamp: bool = True
    reject_empty: bool = True
    schema_version: str = schema_version("host_visible_finalization_policy")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HostVisibleFinalizationContract:
    required_timestamp_header: str
    timezone: str
    timestamp_sample_iso: str
    timestamp_source: str
    timestamp_trusted: bool
    author_id: str
    author_label: str
    author_source: str
    state_emoticon: str
    turn_id: str
    trace_id: str
    policy: HostVisibleFinalizationPolicy = field(default_factory=HostVisibleFinalizationPolicy)
    runtime_version: str = PACKAGE_VERSION_FULL
    contract_hash: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "required_timestamp_header", "timezone", "timestamp_sample_iso", "timestamp_source",
            "author_id", "author_label", "author_source", "state_emoticon", "turn_id", "trace_id",
        ):
            value = str(getattr(self, field_name) or "").strip()
            if not value:
                raise ValueError(f"{field_name} is required")
            setattr(self, field_name, value)
        if not TIMESTAMP_HEADER_RE.fullmatch(self.required_timestamp_header):
            raise ValueError("required_timestamp_header has invalid shape")
        envelope = self.envelope_for_body("contract-validation")
        if not envelope.timestamp_matches_sample():
            raise ValueError("required_timestamp_header does not match timestamp_sample_iso/timezone")
        calculated = self.calculate_hash()
        if self.contract_hash and self.contract_hash != calculated:
            raise ValueError("contract_hash mismatch")
        self.contract_hash = calculated

    def envelope_for_body(self, body: str) -> MessageEnvelope:
        return MessageEnvelope.build(
            timestamp_header=self.required_timestamp_header,
            timezone=self.timezone,
            timestamp_sample_iso=self.timestamp_sample_iso,
            timestamp_source=self.timestamp_source,
            timestamp_trusted=self.timestamp_trusted,
            author_id=self.author_id,
            author_label=self.author_label,
            author_source=self.author_source,
            state_emoticon=self.state_emoticon,
            body=body,
        )

    def calculate_hash(self) -> str:
        payload = {
            "required_timestamp_header": self.required_timestamp_header,
            "timezone": self.timezone,
            "timestamp_sample_iso": self.timestamp_sample_iso,
            "timestamp_source": self.timestamp_source,
            "timestamp_trusted": self.timestamp_trusted,
            "author_id": self.author_id,
            "author_label": self.author_label,
            "author_source": self.author_source,
            "state_emoticon": self.state_emoticon,
            "turn_id": self.turn_id,
            "trace_id": self.trace_id,
            "policy": self.policy.to_dict(),
            "runtime_version": self.runtime_version,
            "schema_version": self.schema_version,
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HostVisibleFinalizationResult:
    accepted: bool
    state: str
    final_visible_text: str
    turn_id: str
    trace_id: str
    contract_hash: str
    original_text_sha256: str
    final_text_sha256: str
    supplied_text_sha256: str | None
    hash_valid: bool
    approval_stage: str
    body_unchanged: bool
    envelope_completed: bool
    violations: list[HostVisibleFinalizationViolation] = field(default_factory=list)
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = SCHEMA_VERSION

    @property
    def repaired(self) -> bool:
        return self.envelope_completed

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["repaired"] = self.repaired
        return payload


class HostVisibleFinalizationGate:
    """Single fail-closed gate for host-authored visible text."""

    def finalize(
        self,
        contract: HostVisibleFinalizationContract,
        text: str,
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
        supplied_text_sha256: str | None = None,
    ) -> HostVisibleFinalizationResult:
        original = canonicalize_host_visible_text(text)
        original_hash = _sha_text(original)
        supplied_hash = str(supplied_text_sha256 or "").strip().lower() or None
        violations: list[HostVisibleFinalizationViolation] = []

        if turn_id is not None and str(turn_id) != contract.turn_id:
            violations.append(HostVisibleFinalizationViolation("turn_id_mismatch", "The supplied turn_id does not match the contract."))
        if trace_id is not None and str(trace_id) != contract.trace_id:
            violations.append(HostVisibleFinalizationViolation("trace_id_mismatch", "The supplied trace_id does not match the contract."))
        if contract.policy.reject_empty and not original.strip():
            violations.append(HostVisibleFinalizationViolation("empty_text", "Visible text is empty."))
        if len(original.encode("utf-8")) > contract.policy.max_utf8_bytes:
            violations.append(HostVisibleFinalizationViolation("text_too_large", "Visible text exceeds the contract byte limit."))
        if contract.policy.require_supplied_text_hash and supplied_hash is None:
            violations.append(HostVisibleFinalizationViolation("text_hash_missing", "Explicit host-finalize approval hash is required."))
        elif supplied_hash is not None and supplied_hash != original_hash:
            violations.append(HostVisibleFinalizationViolation("text_hash_mismatch", "The supplied host-finalize hash does not match the visible text."))

        expected_prefix = f"{contract.required_timestamp_header}\n{contract.state_emoticon} {contract.author_label}\n\n"
        exact_envelope = original.startswith(expected_prefix)
        first_line = original.split("\n", 1)[0].strip() if original else ""
        foreign_timestamp = bool(TIMESTAMP_HEADER_RE.fullmatch(first_line) and first_line != contract.required_timestamp_header)
        malformed_runtime_envelope = bool(original.startswith(contract.required_timestamp_header) and not exact_envelope)
        if foreign_timestamp and contract.policy.reject_foreign_timestamp:
            violations.append(HostVisibleFinalizationViolation("foreign_timestamp", "A timestamp differs from the required runtime timestamp."))
        if malformed_runtime_envelope:
            violations.append(HostVisibleFinalizationViolation("malformed_message_envelope", "The supplied runtime timestamp is followed by an invalid author/affect envelope."))

        fatal = [item for item in violations if not item.repairable]
        if fatal:
            return HostVisibleFinalizationResult(
                accepted=False,
                state="reject",
                final_visible_text="",
                turn_id=contract.turn_id,
                trace_id=contract.trace_id,
                contract_hash=contract.contract_hash,
                original_text_sha256=original_hash,
                final_text_sha256=_sha_text(""),
                supplied_text_sha256=supplied_hash,
                hash_valid=False,
                approval_stage="host_finalize_rejected",
                body_unchanged=False,
                envelope_completed=False,
                violations=violations,
            )

        if exact_envelope:
            final_text = original
            envelope_completed = False
        elif contract.policy.render_body_when_envelope_missing:
            final_text = contract.envelope_for_body(original).render()
            envelope_completed = True
            violations.append(HostVisibleFinalizationViolation(
                "message_envelope_completed",
                "The verified runtime envelope was rendered around the supplied body.",
                True,
            ))
        else:
            violations.append(HostVisibleFinalizationViolation("message_envelope_missing", "The verified runtime envelope is missing."))
            return HostVisibleFinalizationResult(
                accepted=False, state="reject", final_visible_text="", turn_id=contract.turn_id,
                trace_id=contract.trace_id, contract_hash=contract.contract_hash,
                original_text_sha256=original_hash, final_text_sha256=_sha_text(""),
                supplied_text_sha256=supplied_hash, hash_valid=False,
                approval_stage="host_finalize_rejected", body_unchanged=False,
                envelope_completed=False, violations=violations,
            )

        return HostVisibleFinalizationResult(
            accepted=True,
            state="approved_envelope_completion" if envelope_completed else "approved",
            final_visible_text=final_text,
            turn_id=contract.turn_id,
            trace_id=contract.trace_id,
            contract_hash=contract.contract_hash,
            original_text_sha256=original_hash,
            final_text_sha256=_sha_text(final_text),
            supplied_text_sha256=supplied_hash,
            hash_valid=supplied_hash == original_hash,
            approval_stage="host_finalize_hash_approval",
            body_unchanged=(not envelope_completed or final_text.endswith(original)),
            envelope_completed=envelope_completed,
            violations=violations,
        )


def finalize_host_visible_text(
    *,
    required_timestamp_header: str,
    timezone: str,
    timestamp_sample_iso: str,
    timestamp_source: str,
    timestamp_trusted: bool,
    author_id: str,
    author_label: str,
    author_source: str,
    state_emoticon: str,
    turn_id: str,
    trace_id: str,
    text: str,
    supplied_turn_id: str | None = None,
    supplied_trace_id: str | None = None,
    supplied_text_sha256: str | None = None,
    max_utf8_bytes: int = 2 * 1024 * 1024,
) -> HostVisibleFinalizationResult:
    contract = HostVisibleFinalizationContract(
        required_timestamp_header=required_timestamp_header,
        timezone=timezone,
        timestamp_sample_iso=timestamp_sample_iso,
        timestamp_source=timestamp_source,
        timestamp_trusted=timestamp_trusted,
        author_id=author_id,
        author_label=author_label,
        author_source=author_source,
        state_emoticon=state_emoticon,
        turn_id=turn_id,
        trace_id=trace_id,
        policy=HostVisibleFinalizationPolicy(max_utf8_bytes=max_utf8_bytes),
    )
    return HostVisibleFinalizationGate().finalize(
        contract,
        text,
        turn_id=supplied_turn_id,
        trace_id=supplied_trace_id,
        supplied_text_sha256=supplied_text_sha256,
    )
