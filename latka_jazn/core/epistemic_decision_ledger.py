from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import sqlite3
import time

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("epistemic_decision_ledger")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    """Append-only, hash-chained audit ledger for visible epistemic decisions.

    This stores decisions and evidence metadata, never private model reasoning.
    The chain makes deletion/reordering detectable by validation.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.executescript(
            """
            PRAGMA journal_mode=WAL;
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
            CREATE INDEX IF NOT EXISTS idx_epistemic_turn ON epistemic_decisions(turn_id, trace_id, seq);
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
        assessments: Iterable[dict[str, Any]],
    ) -> list[EpistemicLedgerEntry]:
        out: list[EpistemicLedgerEntry] = []
        previous = self._previous_hash()
        for assessment in assessments:
            payload = dict(assessment or {})
            created = time.time()
            matched = str(payload.get("matched_text") or "")
            material = {
                "turn_id": turn_id,
                "trace_id": trace_id,
                "claim_kind": str(payload.get("kind") or "unknown"),
                "claim_status": str(payload.get("status") or "unknown"),
                "matched_text_sha256": _sha(matched),
                "reason": str(payload.get("reason") or "unknown"),
                "required_evidence": list(payload.get("required_evidence") or []),
                "evidence_snapshot": dict(payload.get("evidence_snapshot") or {}),
                "previous_entry_sha256": previous,
                "created_at_unix": created,
                "schema_version": SCHEMA_VERSION,
            }
            digest = _sha(_canonical(material))
            entry = EpistemicLedgerEntry(
                turn_id=turn_id,
                trace_id=trace_id,
                claim_kind=material["claim_kind"],
                claim_status=material["claim_status"],
                matched_text_sha256=material["matched_text_sha256"],
                reason=material["reason"],
                required_evidence=tuple(material["required_evidence"]),
                evidence_snapshot=material["evidence_snapshot"],
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
        return out

    def validate_chain(self) -> dict[str, Any]:
        integrity = str(self.con.execute("PRAGMA quick_check").fetchone()[0])
        if integrity != "ok":
            return {"ok": False, "reason": f"sqlite_integrity={integrity}"}
        previous: str | None = None
        checked = 0
        rows = self.con.execute("SELECT * FROM epistemic_decisions ORDER BY seq ASC").fetchall()
        for row in rows:
            material = {
                "turn_id": row["turn_id"],
                "trace_id": row["trace_id"],
                "claim_kind": row["claim_kind"],
                "claim_status": row["claim_status"],
                "matched_text_sha256": row["matched_text_sha256"],
                "reason": row["reason"],
                "required_evidence": json.loads(row["required_evidence_json"]),
                "evidence_snapshot": json.loads(row["evidence_snapshot_json"]),
                "previous_entry_sha256": row["previous_entry_sha256"],
                "created_at_unix": float(row["created_at_unix"]),
                "schema_version": row["schema_version"],
            }
            expected = _sha(_canonical(material))
            if row["previous_entry_sha256"] != previous:
                return {"ok": False, "reason": "previous_hash_mismatch", "seq": row["seq"]}
            if row["entry_sha256"] != expected:
                return {"ok": False, "reason": "entry_hash_mismatch", "seq": row["seq"]}
            previous = str(row["entry_sha256"])
            checked += 1
        return {"ok": True, "checked_entries": checked, "head_sha256": previous}
