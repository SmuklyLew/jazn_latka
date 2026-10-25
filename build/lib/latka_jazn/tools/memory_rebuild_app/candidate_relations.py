from __future__ import annotations

from typing import Any, Iterable
import uuid

from .unified_contracts import UnifiedMixinHost
from .unified_schema import CANONICAL_DATABASE_NAME, json_text, sha_text, utc_now


class CandidateRelationsMixin(UnifiedMixinHost):
    def merge_candidates(self, candidate_ids: Iterable[str], *, title: str, summary: str, edited_by: str, reason: str) -> dict[str, Any]:
        ids = list(dict.fromkeys(str(item) for item in candidate_ids if str(item).strip()))
        if len(ids) < 2:
            raise ValueError("Połączenie wymaga co najmniej dwóch kandydatów.")
        sources = [self.get_candidate(item) for item in ids]
        identity = sha_text(json_text(["merged", sorted(ids), title, summary]))
        candidate_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"jazn-candidate:{identity}"))
        domains = sorted({domain for item in sources for domain in item.get("domains", [])})
        confidence = max(float(item.get("confidence") or 0.0) for item in sources)
        importance = max(float(item.get("importance") or 0.0) for item in sources)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute(
                    "INSERT INTO candidates(candidate_id,identity_key,source_database,source_type,source_record_id,source_sha256,title,summary,truth_status,confidence,importance,domains_json,score_json,status,created_at_utc,reviewed_at_utc,reviewed_by,review_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending_review',?,?,?,?)",
                    (candidate_id, identity, CANONICAL_DATABASE_NAME, "merged_candidates", ",".join(ids), None, title, summary, "inferred", confidence, importance, json_text(domains), json_text({"merged_from": ids}), utc_now(), utc_now(), edited_by, reason),
                )
                for source_id in ids:
                    con.execute(
                        "UPDATE candidates SET status='merged',reviewed_at_utc=?,reviewed_by=?,review_reason=? WHERE candidate_id=?",
                        (utc_now(), edited_by, reason, source_id),
                    )
                    con.execute(
                        "INSERT OR IGNORE INTO candidate_links(link_id,source_candidate_id,target_candidate_id,relation,note,created_at_utc,created_by) VALUES(?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), source_id, candidate_id, "merged_into", reason, utc_now(), edited_by),
                    )
                con.commit()
            except BaseException:
                con.rollback()
                raise
        return self.get_candidate(candidate_id)

    def split_candidate(self, candidate_id: str, *, title: str, summary: str, edited_by: str, reason: str) -> dict[str, Any]:
        source = self.get_candidate(candidate_id)
        identity = sha_text(json_text(["split", candidate_id, title, summary]))
        new_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"jazn-candidate:{identity}"))
        with self.connect() as con:
            con.execute(
                "INSERT INTO candidates(candidate_id,identity_key,source_database,source_type,source_record_id,source_sha256,title,summary,truth_status,confidence,importance,domains_json,score_json,status,created_at_utc,reviewed_at_utc,reviewed_by,review_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending_review',?,?,?,?)",
                (new_id, identity, CANONICAL_DATABASE_NAME, "split_candidate", candidate_id, source.get("source_sha256"), title, summary, source.get("truth_status") or "inferred", source.get("confidence") or 0.5, source.get("importance") or 0.5, json_text(source.get("domains") or []), json_text({"split_from": candidate_id}), utc_now(), utc_now(), edited_by, reason),
            )
            con.execute(
                "INSERT INTO candidate_links(link_id,source_candidate_id,target_candidate_id,relation,note,created_at_utc,created_by) VALUES(?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), candidate_id, new_id, "split_into", reason, utc_now(), edited_by),
            )
            con.commit()
        return self.get_candidate(new_id)
