from __future__ import annotations

from typing import Any, Mapping
import uuid

from latka_jazn.tools.memory_rebuild_experience import ExperienceStore

from .unified_contracts import UnifiedMixinHost
from .unified_schema import EDITABLE_CANDIDATE_FIELDS, candidate_snapshot, json_text, quote, sha_text, utc_now


class CandidateEditorMixin(UnifiedMixinHost):
    def list_candidates(self, *, status: str | None = None, limit: int = 200, query: str | None = None) -> list[dict[str, Any]]:
        self.initialize()
        sql = "SELECT * FROM candidates"
        clauses: list[str] = []
        params: list[Any] = []
        if status and status != "all":
            clauses.append("status=?")
            params.append(status)
        if query:
            clauses.append("(title LIKE ? OR summary LIKE ?)")
            marker = f"%{query}%"
            params.extend((marker, marker))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY importance DESC,confidence DESC,created_at_utc,candidate_id LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connect(read_only=True) as con:
            return [candidate_snapshot(row) for row in con.execute(sql, params).fetchall()]

    def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        self.initialize()
        with self.connect(read_only=True) as con:
            row = con.execute("SELECT * FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            item = candidate_snapshot(row)
            item["revisions"] = [dict(value) for value in con.execute(
                "SELECT * FROM candidate_revisions WHERE candidate_id=? ORDER BY revision DESC", (candidate_id,),
            ).fetchall()]
            item["evidence"] = [dict(value) for value in con.execute(
                "SELECT * FROM candidate_evidence WHERE candidate_id=? ORDER BY evidence_key", (candidate_id,),
            ).fetchall()]
            item["links"] = [dict(value) for value in con.execute(
                "SELECT * FROM candidate_links WHERE source_candidate_id=? OR target_candidate_id=? ORDER BY created_at_utc",
                (candidate_id, candidate_id),
            ).fetchall()]
            return item

    def edit_candidate(self, candidate_id: str, changes: Mapping[str, Any], *, edited_by: str, reason: str) -> dict[str, Any]:
        if not edited_by.strip() or not reason.strip():
            raise ValueError("edited_by i reason są wymagane")
        normalized = {key: value for key, value in changes.items() if key in EDITABLE_CANDIDATE_FIELDS}
        if not normalized:
            raise ValueError("Brak obsługiwanych pól do zmiany.")
        for key in ("confidence", "importance"):
            if key in normalized:
                normalized[key] = max(0.0, min(1.0, float(normalized[key])))
        for key in ("domains_json", "score_json"):
            if key in normalized and not isinstance(normalized[key], str):
                normalized[key] = json_text(normalized[key])
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row = con.execute("SELECT * FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
                if row is None:
                    raise KeyError(candidate_id)
                revision = int(con.execute(
                    "SELECT COALESCE(MAX(revision),0)+1 FROM candidate_revisions WHERE candidate_id=?", (candidate_id,),
                ).fetchone()[0])
                con.execute(
                    "INSERT INTO candidate_revisions(revision_id,candidate_id,revision,snapshot_json,changed_fields_json,edited_at_utc,edited_by,reason) VALUES(?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), candidate_id, revision, json_text(dict(row)), json_text(normalized), utc_now(), edited_by.strip(), reason.strip()),
                )
                assignments = ",".join(f"{quote(key)}=?" for key in normalized)
                con.execute(f"UPDATE candidates SET {assignments} WHERE candidate_id=?", [*normalized.values(), candidate_id])
                con.commit()
            except BaseException:
                con.rollback()
                raise
        return self.get_candidate(candidate_id)

    def add_candidate_evidence(
        self,
        candidate_id: str,
        *,
        source_database: str,
        source_type: str,
        source_record_id: str,
        excerpt: str = "",
        context_before: str = "",
        context_after: str = "",
        source_sha256: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence_key = sha_text(json_text([source_database, source_type, source_record_id, source_sha256, excerpt]))
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO candidate_evidence(candidate_id,evidence_key,source_database,source_type,source_record_id,source_sha256,excerpt,context_before,context_after,evidence_json,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (candidate_id, evidence_key, source_database, source_type, source_record_id, source_sha256, excerpt, context_before, context_after, json_text(dict(details or {})), utc_now()),
            )
            con.commit()
        return self.get_candidate(candidate_id)

    def review_candidate(self, candidate_id: str, *, decision: str, reviewed_by: str, reason: str) -> dict[str, Any]:
        decision = decision.strip().lower()
        if decision == "approve":
            self.edit_candidate(
                candidate_id,
                {"reviewed_at_utc": utc_now(), "reviewed_by": reviewed_by, "review_reason": reason},
                edited_by=reviewed_by,
                reason=f"review:approve:{reason}",
            )
            with ExperienceStore(self.path) as experience:
                return experience.approve(candidate_id, candidate_id, reviewed_by, reason)
        status = {"reject": "rejected_operator", "pending": "pending_review"}.get(decision)
        if status is None:
            raise ValueError("decision musi mieć wartość approve, reject albo pending")
        return self.edit_candidate(
            candidate_id,
            {"status": status, "reviewed_at_utc": utc_now(), "reviewed_by": reviewed_by, "review_reason": reason},
            edited_by=reviewed_by,
            reason=f"review:{decision}:{reason}",
        )
