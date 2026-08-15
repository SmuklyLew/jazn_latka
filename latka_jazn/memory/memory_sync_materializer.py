from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from latka_jazn.memory.memory_promotion import PromotionDecision, PromotionOutcome, PromotionRequest
from latka_jazn.memory.memory_sync_contracts import MemorySyncContractError
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tier_support import record_from_dict
from latka_jazn.memory.memory_tiers import LongTermMemoryRecord, MemoryTier, ShortTermMemoryRecord


@dataclass(slots=True, frozen=True)
class MemoryMaterializationResult:
    applied: bool
    event_type: str
    records_written: int = 0
    promotions_written: int = 0
    reason: str = ""


class MemorySyncEventMaterializer:
    """Apply decrypted sync payloads through canonical memory-domain APIs.

    Remote data never contains executable SQL. Unknown event types fail closed. L3
    restoration is accepted only when the payload contains a valid promotion request,
    decision, and matching long-term record; the materializer also suppresses a new
    outbox event to avoid replication echo loops.
    """

    SUPPORTED_EVENT_TYPES = frozenset({"memory.runtime_turn_staged", "memory.promotion"})

    def __init__(self, store: MemoryTierStore) -> None:
        self.store = store

    def apply(self, *, event_type: str, payload: Mapping[str, Any]) -> MemoryMaterializationResult:
        if event_type not in self.SUPPORTED_EVENT_TYPES:
            raise MemorySyncContractError(f"unsupported remote memory event type: {event_type}")
        if int(payload.get("record_payload_version") or 0) != 1:
            raise MemorySyncContractError("unsupported or missing record_payload_version")
        if event_type == "memory.runtime_turn_staged":
            return self._apply_runtime_turn(payload)
        return self._apply_promotion(payload)

    def _apply_runtime_turn(self, payload: Mapping[str, Any]) -> MemoryMaterializationResult:
        raw_records = payload.get("records")
        if not isinstance(raw_records, list) or len(raw_records) != 2:
            raise MemorySyncContractError("runtime-turn sync payload must contain exactly two records")
        records = []
        for item in raw_records:
            if not isinstance(item, dict):
                raise MemorySyncContractError("runtime-turn record payload must be an object")
            records.append(record_from_dict(item))
        tiers = {record.tier for record in records}
        if tiers != {MemoryTier.WORKING, MemoryTier.SHORT_TERM}:
            raise MemorySyncContractError("runtime-turn payload must contain one working and one short-term record")
        records_written = 0
        with self.store.transaction():
            for record in records:
                records_written += self.store.write_record(record).records_written
        return MemoryMaterializationResult(
            applied=True,
            event_type="memory.runtime_turn_staged",
            records_written=records_written,
            reason="canonical_records_materialized",
        )

    def _apply_promotion(self, payload: Mapping[str, Any]) -> MemoryMaterializationResult:
        source_raw = payload.get("source_record")
        request_raw = payload.get("request")
        decision_raw = payload.get("decision")
        long_term_raw = payload.get("long_term_record")
        if not isinstance(source_raw, dict) or not isinstance(request_raw, dict) or not isinstance(decision_raw, dict):
            raise MemorySyncContractError("promotion payload is missing source/request/decision")
        source = record_from_dict(source_raw)
        if not isinstance(source, ShortTermMemoryRecord):
            raise MemorySyncContractError("promotion source must be short-term memory")
        request = PromotionRequest(
            request_id=str(request_raw.get("request_id") or ""),
            source_memory_id=str(request_raw.get("source_memory_id") or ""),
            target_tier=MemoryTier(str(request_raw.get("target_tier") or "")),
            requested_by=str(request_raw.get("requested_by") or ""),
            requested_at_utc=_parse_datetime(request_raw.get("requested_at_utc")),
            explicit_user_approval=bool(request_raw.get("explicit_user_approval")),
            reason=str(request_raw.get("reason") or ""),
        )
        reasons = decision_raw.get("reasons")
        if not isinstance(reasons, (list, tuple)):
            raise MemorySyncContractError("promotion decision reasons must be a list")
        decision = PromotionDecision(
            decision_id=str(decision_raw.get("decision_id") or ""),
            request_id=str(decision_raw.get("request_id") or ""),
            source_memory_id=str(decision_raw.get("source_memory_id") or ""),
            outcome=PromotionOutcome(str(decision_raw.get("outcome") or "")),
            target_tier=MemoryTier(str(decision_raw.get("target_tier") or "")),
            decided_at_utc=_parse_datetime(decision_raw.get("decided_at_utc")),
            decided_by=str(decision_raw.get("decided_by") or ""),
            reasons=tuple(str(value) for value in reasons),
            policy_version=str(decision_raw.get("policy_version") or ""),
            automatic_commit_allowed=bool(decision_raw.get("automatic_commit_allowed", False)),
        )
        long_term: LongTermMemoryRecord | None = None
        if long_term_raw is not None:
            if not isinstance(long_term_raw, dict):
                raise MemorySyncContractError("long_term_record must be an object or null")
            candidate = record_from_dict(long_term_raw)
            if not isinstance(candidate, LongTermMemoryRecord):
                raise MemorySyncContractError("long_term_record is not a long-term memory record")
            long_term = candidate
        with self.store.transaction():
            summary = self.store.write_promotion(
                source,
                request,
                decision,
                long_term,
                emit_outbox=False,
            )
        return MemoryMaterializationResult(
            applied=True,
            event_type="memory.promotion",
            records_written=summary.records_written,
            promotions_written=summary.promotions_written,
            reason="promotion_ledger_materialized_without_replication_echo",
        )


def _parse_datetime(value: Any) -> datetime:
    text = str(value or "")
    if not text:
        raise MemorySyncContractError("required datetime is missing")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise MemorySyncContractError("datetime must include timezone")
    return parsed


__all__ = ["MemoryMaterializationResult", "MemorySyncEventMaterializer"]
