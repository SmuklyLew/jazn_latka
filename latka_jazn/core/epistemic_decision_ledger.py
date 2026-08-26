from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import json
import time

from latka_jazn.db.runtime_sqlite import (
    connect_runtime_writable,
    runtime_sqlite_write_guard,
)
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("epistemic_decision_ledger")
_BLOCKED_KEYS = ("chain_of_thought", "reasoning_trace", "raw_prompt", "raw_content", "secret", "token")
_WRITE_TIMEOUT_MS = 30_000


def epistemic_ledger_path(runtime_workspace: str | Path) -> Path:
    return Path(runtime_workspace).expanduser().resolve() / "epistemic_decisions.sqlite3"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded(value: Any, *, depth: int = 0) -> Any:
    if depth >= 6:
        return "[TRUNCATED_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:512]
    if isinstance(value, (list, tuple)):
        return [_bounded(item, depth=depth + 1) for item in value[:32]]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:48]:
            key = str(raw_key)[:96]
            folded = key.casefold()
            if any(blocked in folded for blocked in _BLOCKED_KEYS):
                continue
            result[key] = _bounded(raw_value, depth=depth + 1)
        return result
    return str(value)[:256]


@dataclass(slots=True, frozen=True)
class EpistemicLedgerEntry:
    turn_id: str
    trace_id: str
    claim_kind: str
    claim_status: str
    matched_text_sha256: str
    reason: str
    required_evidence: tuple[str, ...]
    evidence_snapshot: dict[str, Any]
    previous_entry_sha256: str | None
    entry_sha256: str
    created_at_unix: float
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EpistemicDecisionLedger:
    """Append-only hash chain of bounded decisions, never private reasoning.

    The ledger is an active runtime writer. It therefore uses the same canonical
    SQLite connection and cross-process write guard as the rest of the runtime
    instead of forcing WAL independently. This keeps the journal-mode policy
    aligned with the actually loaded SQLite build and protects hard-isolated
    turn workers from concurrent writer races.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = connect_runtime_writable(self.path, timeout_ms=_WRITE_TIMEOUT_MS)
        self._init_schema()

    def __enter__(self) -> "EpistemicDecisionLedger":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _init_schema(self) -> None:
        with runtime_sqlite_write_guard(self.path, timeout_ms=_WRITE_TIMEOUT_MS):
            self.con.executescript(
                """
                CREATE TABLE IF NOT EXISTS epistemic_decisions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    claim_kind TEXT NOT NULL,
                    claim_status TEXT NOT NULL,
                    matched_text_sha256 TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    required_evidence_json TEXT NOT NULL,
                    evidence_snapshot_json TEXT NOT NULL,
                    previous_entry_sha256 TEXT,
                    entry_sha256 TEXT NOT NULL UNIQUE,
                    created_at_unix REAL NOT NULL,
                    schema_version TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_epistemic_turn
                    ON epistemic_decisions(turn_id, trace_id, seq);
                """
            )
            self.con.commit()

    def close(self) -> None:
        self.con.close()

    def _previous_hash(self) -> str | None:
        row = self.con.execute(
            "SELECT entry_sha256 FROM epistemic_decisions ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return str(row[0]) if row else None

    def append_assessments(
        self,
        *,
        turn_id: str,
        trace_id: str,
        assessments: Iterable[Mapping[str, Any]],
    ) -> list[EpistemicLedgerEntry]:
        if not str(turn_id).strip() or not str(trace_id).strip():
            raise ValueError("turn_id and trace_id are required")
        out: list[EpistemicLedgerEntry] = []
        with runtime_sqlite_write_guard(self.path, timeout_ms=_WRITE_TIMEOUT_MS):
            self.con.execute("BEGIN IMMEDIATE")
            try:
                previous = self._previous_hash()
                for assessment in assessments:
                    payload = dict(assessment or {})
                    created = time.time()
                    required = tuple(str(item)[:160] for item in payload.get("required_evidence") or ())[:32]
                    evidence = _bounded(payload.get("evidence_snapshot") or {})
                    evidence = evidence if isinstance(evidence, dict) else {}
                    material = {
                        "turn_id": str(turn_id)[:160],
                        "trace_id": str(trace_id)[:160],
                        "claim_kind": str(payload.get("kind") or "unknown")[:96],
                        "claim_status": str(payload.get("status") or "unknown")[:96],
                        "matched_text_sha256": _sha(str(payload.get("matched_text") or "")),
                        "reason": str(payload.get("reason") or "unknown")[:256],
                        "required_evidence": list(required),
                        "evidence_snapshot": evidence,
                        "previous_entry_sha256": previous,
                        "created_at_unix": created,
                        "schema_version": SCHEMA_VERSION,
                    }
                    digest = _sha(_canonical(material))
                    entry = EpistemicLedgerEntry(
                        turn_id=material["turn_id"],
                        trace_id=material["trace_id"],
                        claim_kind=material["claim_kind"],
                        claim_status=material["claim_status"],
                        matched_text_sha256=material["matched_text_sha256"],
                        reason=material["reason"],
                        required_evidence=required,
                        evidence_snapshot=evidence,
                        previous_entry_sha256=previous,
                        entry_sha256=digest,
                        created_at_unix=created,
                    )
                    self.con.execute(
                        """
                        INSERT INTO epistemic_decisions(
                            turn_id,trace_id,claim_kind,claim_status,matched_text_sha256,reason,
                            required_evidence_json,evidence_snapshot_json,previous_entry_sha256,
                            entry_sha256,created_at_unix,schema_version
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            entry.turn_id,
                            entry.trace_id,
                            entry.claim_kind,
                            entry.claim_status,
                            entry.matched_text_sha256,
                            entry.reason,
                            _canonical(list(entry.required_evidence)),
                            _canonical(entry.evidence_snapshot),
                            entry.previous_entry_sha256,
                            entry.entry_sha256,
                            entry.created_at_unix,
                            entry.schema_version,
                        ),
                    )
                    previous = digest
                    out.append(entry)
                self.con.commit()
            except Exception:
                self.con.rollback()
                raise
        return out

    def validate_chain(self) -> dict[str, Any]:
        integrity = str(self.con.execute("PRAGMA quick_check").fetchone()[0])
        if integrity != "ok":
            return {"ok": False, "reason": f"sqlite_integrity={integrity}"}
        previous: str | None = None
        checked = 0
        rows = self.con.execute("SELECT * FROM epistemic_decisions ORDER BY seq ASC").fetchall()
        for row in rows:
            try:
                required = json.loads(row["required_evidence_json"])
                evidence = json.loads(row["evidence_snapshot_json"])
            except (TypeError, json.JSONDecodeError):
                return {"ok": False, "reason": "ledger_json_invalid", "seq": row["seq"]}
            material = {
                "turn_id": row["turn_id"],
                "trace_id": row["trace_id"],
                "claim_kind": row["claim_kind"],
                "claim_status": row["claim_status"],
                "matched_text_sha256": row["matched_text_sha256"],
                "reason": row["reason"],
                "required_evidence": required,
                "evidence_snapshot": evidence,
                "previous_entry_sha256": row["previous_entry_sha256"],
                "created_at_unix": float(row["created_at_unix"]),
                "schema_version": row["schema_version"],
            }
            if row["previous_entry_sha256"] != previous:
                return {"ok": False, "reason": "previous_hash_mismatch", "seq": row["seq"]}
            expected = _sha(_canonical(material))
            if row["entry_sha256"] != expected:
                return {"ok": False, "reason": "entry_hash_mismatch", "seq": row["seq"]}
            previous = str(row["entry_sha256"])
            checked += 1
        return {"ok": True, "checked_entries": checked, "head_sha256": previous}
