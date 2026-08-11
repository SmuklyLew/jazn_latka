from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.core.json_types import json_object
from latka_jazn.memory.memory_tier_store import MemoryTierStore, WorkingMemoryBudget
from latka_jazn.memory.memory_tiers import (
    MemoryKind,
    MemoryTier,
    MemoryTruthStatus,
    SourceEvidence,
    WorkingMemoryRecord,
    deterministic_memory_id,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("wake_state_runtime")
TRUTH_BOUNDARY = (
    "Wake state is a verified, bounded continuity packet. It may seed L1 and the model/host context, "
    "but it does not itself promote L2/L3 records or prove biological consciousness."
)


@dataclass(slots=True)
class WakeStateRuntimeStatus:
    schema_version: str
    status: str
    sidecar_db_path: str
    snapshot_id: str | None
    snapshot_sha256: str | None
    source_run_id: str | None
    validation_status: str | None
    context: dict[str, Any] | None
    l1_memory_id: str | None
    errors: list[str]
    continuity_mode: str = "wake_unavailable"
    continuity_claim_allowed: bool = False
    ordinary_dialogue_allowed: bool = True
    degradation_policy: str = "continue_without_wake_context"
    truth_boundary: str = TRUTH_BOUNDARY

    @property
    def ok(self) -> bool:
        return self.status in {"ready", "hydrated"}

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ok": self.ok}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    recent_value = snapshot.get("recent_events")
    recent: list[Any] = recent_value if isinstance(recent_value, list) else []
    threads_value = snapshot.get("open_threads")
    threads: list[Any] = threads_value if isinstance(threads_value, list) else []
    relationship = json_object(snapshot.get("relationship_digest"))
    truth = json_object(snapshot.get("truth_boundary_digest"))
    policy = json_object(snapshot.get("namespace_policy"))
    return {
        "schema_version": SCHEMA_VERSION,
        "wake_state_schema_version": snapshot.get("schema_version"),
        "created_at_utc": snapshot.get("created_at_utc"),
        "identity_snapshot": snapshot.get("identity_snapshot") if isinstance(snapshot.get("identity_snapshot"), dict) else {},
        "relationship_digest": {
            "krzysztof_candidate_present": bool(relationship.get("krzysztof_candidate_present")),
            "krzysztof_private_namespace_allowed": bool(relationship.get("krzysztof_private_namespace_allowed")),
            "rule": relationship.get("rule"),
        },
        "truth_boundary_digest": truth,
        "namespace_policy": {
            "default_for_unknown_interlocutor": policy.get("default_for_unknown_interlocutor"),
            "private_namespace_requires_confirmed_actor": bool(policy.get("private_namespace_requires_confirmed_actor", True)),
            "namespace_counts": json_object(policy.get("namespace_counts")),
        },
        "recent_events": recent[:8],
        "open_threads": [str(item)[:320] for item in threads[:8]],
        "source_counts": json_object(snapshot.get("source_counts")),
        "normalization_coverage": json_object(snapshot.get("normalization_coverage")),
        "source_run_id": snapshot.get("source_run_id"),
        "validation_status": snapshot.get("validation_status"),
        "truth_boundary": TRUTH_BOUNDARY,
    }


class WakeStateRuntimeBridge:
    def __init__(self, config: JaznConfig) -> None:
        self.config = config
        self.sidecar_path = config.normalization_sidecar_db_path
        self.tier_path = config.memory_tier_db_path

    def load(self) -> WakeStateRuntimeStatus:
        if not self.sidecar_path.is_file():
            return self._status("sidecar_missing", errors=[f"missing sidecar: {self.sidecar_path}"])
        try:
            con = sqlite3.connect(f"file:{self.sidecar_path.resolve().as_posix()}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            try:
                tables = {
                    str(row[0])
                    for row in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")
                }
                required_tables = {"wake_state_snapshots", "normalization_runs"}
                missing_tables = sorted(required_tables - tables)
                if missing_tables:
                    return self._status(
                        "sidecar_schema_missing",
                        errors=[f"missing table: {name}" for name in missing_tables],
                    )
                run_columns = {str(row[1]) for row in con.execute("PRAGMA table_info(normalization_runs)")}
                coverage_columns = {"expected_item_count", "normalized_item_count", "coverage_complete"}
                if not coverage_columns.issubset(run_columns):
                    return self._status(
                        "normalization_coverage_unverified",
                        errors=["normalization run does not expose complete coverage metadata"],
                    )
                integrity = str(con.execute("PRAGMA quick_check").fetchone()[0])
                fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
                rows = con.execute(
                    "SELECT * FROM wake_state_snapshots WHERE active=1 ORDER BY created_at_utc DESC,rowid DESC"
                ).fetchall()
            finally:
                con.close()
            if integrity != "ok" or fk_count:
                return self._status("sidecar_invalid", errors=[f"integrity={integrity}; foreign_keys={fk_count}"])
            if len(rows) != 1:
                return self._status("active_snapshot_invalid", errors=[f"active_snapshot_count={len(rows)}"])
            row = rows[0]
            raw = str(row["snapshot_json"])
            digest = _sha256_text(raw)
            if digest != str(row["snapshot_sha256"]):
                return self._status("snapshot_hash_mismatch", errors=["snapshot_json sha256 mismatch"])
            snapshot = json.loads(raw)
            if not isinstance(snapshot, dict) or str(row["validation_status"]) != "valid":
                return self._status("snapshot_not_valid", errors=[f"validation_status={row['validation_status']}"])
            source_run_id = str(row["source_run_id"] or "")
            if not source_run_id:
                return self._status("source_run_invalid", errors=["wake snapshot has no source_run_id"])
            run = None
            check = sqlite3.connect(f"file:{self.sidecar_path.resolve().as_posix()}?mode=ro", uri=True)
            check.row_factory = sqlite3.Row
            try:
                run = check.execute(
                    "SELECT status,ended_at_utc,dry_run,expected_item_count,normalized_item_count,coverage_complete "
                    "FROM normalization_runs WHERE run_id=?",
                    (source_run_id,),
                ).fetchone()
            finally:
                check.close()
            if run is None or str(run["status"]) != "ok" or not run["ended_at_utc"] or int(run["dry_run"]):
                return self._status("source_run_invalid", errors=["wake snapshot source normalization run is invalid"])
            expected = int(run["expected_item_count"] or 0)
            normalized = int(run["normalized_item_count"] or 0)
            if not bool(run["coverage_complete"]) or normalized < expected:
                return self._status(
                    "normalization_partial",
                    errors=[f"normalization coverage incomplete: {normalized}/{expected}"],
                )
            coverage = json_object(snapshot.get("normalization_coverage"))
            if not coverage or coverage.get("coverage_complete") is not True:
                return self._status(
                    "snapshot_coverage_unverified",
                    errors=["wake snapshot does not carry verified normalization coverage"],
                )
            if int(coverage.get("normalized_item_count") or 0) < int(coverage.get("expected_item_count") or 0):
                return self._status(
                    "snapshot_coverage_unverified",
                    errors=["wake snapshot coverage counts are inconsistent"],
                )
            context = _bounded_snapshot(snapshot)
            return WakeStateRuntimeStatus(
                schema_version=SCHEMA_VERSION,
                status="ready",
                sidecar_db_path=str(self.sidecar_path),
                snapshot_id=str(row["snapshot_id"]),
                snapshot_sha256=str(row["snapshot_sha256"]),
                source_run_id=str(row["source_run_id"] or "") or None,
                validation_status=str(row["validation_status"]),
                context=context,
                l1_memory_id=None,
                errors=[],
                continuity_mode="verified_wake",
                continuity_claim_allowed=True,
                ordinary_dialogue_allowed=True,
                degradation_policy="use_verified_wake_context",
            )
        except (sqlite3.DatabaseError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            return self._status("read_error", errors=[f"{type(exc).__name__}: {exc}"])

    def hydrate_l1(self, *, session_id: str, active_goal: str = "verified_wake_state") -> WakeStateRuntimeStatus:
        status = self.load()
        if not status.ok or not status.context or not status.snapshot_id or not status.snapshot_sha256:
            return status
        content = _canonical_json(status.context)
        now = datetime.now(timezone.utc)
        evidence = SourceEvidence(
            source_type="wake_state_snapshot",
            source_id=status.snapshot_id,
            source_sha256=status.snapshot_sha256,
            exact_excerpt_sha256=_sha256_text(content),
            timestamp_status="snapshot_recorded",
            metadata={
                "sidecar_db_path": str(self.sidecar_path),
                "source_run_id": status.source_run_id,
                "validation_status": status.validation_status,
                "schema_version": SCHEMA_VERSION,
            },
        )
        memory_id = deterministic_memory_id(
            tier=MemoryTier.WORKING,
            kind=MemoryKind.CONVERSATION_CONTEXT,
            content=content,
            domain="runtime_continuity",
            mode="wake_state",
            evidence=(evidence,),
        )
        record = WorkingMemoryRecord(
            memory_id=memory_id,
            tier=MemoryTier.WORKING,
            kind=MemoryKind.CONVERSATION_CONTEXT,
            content=content,
            content_sha256=_sha256_text(content),
            domain="runtime_continuity",
            mode="wake_state",
            truth_status=MemoryTruthStatus.SOURCE_RECORDED,
            confidence=0.9,
            importance=0.86,
            created_at_utc=now,
            updated_at_utc=now,
            evidence=(evidence,),
            tags=("wake_state", "verified", "l1", "transactional_memory"),
            session_id=session_id,
            turn_id=None,
            active_goal=active_goal,
            expires_on_session_end=True,
            checkpoint_allowed=True,
        )
        try:
            with MemoryTierStore(self.tier_path) as store:
                store.save_record(record, working_budget=WorkingMemoryBudget())
            status.status = "hydrated"
            status.l1_memory_id = memory_id
            status.continuity_mode = "verified_wake_hydrated"
            status.continuity_claim_allowed = True
            status.degradation_policy = "use_verified_wake_context"
            return status
        except Exception as exc:
            status.status = "l1_hydration_failed"
            status.errors.append(f"{type(exc).__name__}: {exc}")
            return status

    def end_session(self, session_id: str) -> int:
        if not self.tier_path.is_file():
            return 0
        with MemoryTierStore(self.tier_path) as store:
            return store.end_session(session_id)

    def _status(self, status: str, *, errors: list[str]) -> WakeStateRuntimeStatus:
        return WakeStateRuntimeStatus(
            schema_version=SCHEMA_VERSION,
            status=status,
            sidecar_db_path=str(self.sidecar_path),
            snapshot_id=None,
            snapshot_sha256=None,
            source_run_id=None,
            validation_status=None,
            context=None,
            l1_memory_id=None,
            errors=errors,
            continuity_mode="wake_unavailable",
            continuity_claim_allowed=False,
            ordinary_dialogue_allowed=True,
            degradation_policy="continue_without_wake_context",
        )
