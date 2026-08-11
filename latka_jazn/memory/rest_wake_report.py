from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import sqlite3
import uuid

from latka_jazn.memory.rest_contracts import RestContinuityStatus, canonical_json, sha256_text
from latka_jazn.memory.rest_cycle_store import RestCycleStore
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("rest_wake_report")


class RestWakeReportBuilder:
    def __init__(self, store: RestCycleStore) -> None:
        self.store = store

    def build_and_persist(self, episode_id: str, *, generated_at_utc: str | None = None) -> dict[str, Any]:
        bundle = self.store.episode_bundle(episode_id)
        if not bundle:
            return self._empty(RestContinuityStatus.REST_NONE, "episode_not_found")
        integrity = self.store.validate()
        episode = bundle["episode"]
        cycles = bundle["cycles"]
        scenes = bundle["scenes"]
        evaluations = bundle["evaluations"]
        decisions = bundle["decisions"]
        if not integrity.get("ok"):
            continuity = RestContinuityStatus.REST_INTEGRITY_FAILED
        elif episode.get("status") == "completed" and all(c.get("status") in {"completed", "skipped"} for c in cycles):
            continuity = RestContinuityStatus.REST_VERIFIED
        else:
            continuity = RestContinuityStatus.REST_PARTIAL
        started_ns = int(episode.get("started_monotonic_ns") or 0)
        ended_ns = int(episode.get("ended_monotonic_ns") or 0)
        report = {
            "schema_version": SCHEMA_VERSION,
            "runtime_version": PACKAGE_VERSION_FULL,
            "rest_continuity_status": continuity.value,
            "episode_id": episode_id,
            "episode_status": episode.get("status"),
            "started_at_utc": episode.get("started_at_utc"),
            "ended_at_utc": episode.get("ended_at_utc"),
            "verified_process_elapsed_seconds": max(0.0, (ended_ns - started_ns) / 1_000_000_000) if ended_ns and started_ns else None,
            "verified_idle_window_seconds": (
                (max(0.0, (ended_ns - started_ns) / 1_000_000_000) + float(cycles[0].get("idle_seconds") or 0.0))
                if ended_ns and started_ns and cycles else None
            ),
            "cycle_count": len(cycles),
            "completed_cycle_count": sum(c.get("status") == "completed" for c in cycles),
            "failed_cycle_count": sum(c.get("status") == "failed" for c in cycles),
            "skipped_cycle_count": sum(c.get("status") == "skipped" for c in cycles),
            "replay_item_count": len(bundle["replay_items"]),
            "dream_scene_count": len(scenes),
            "evaluation_count": len(evaluations),
            "consolidation_decision_count": len(decisions),
            "materialized_l2_candidate_count": sum(bool(d.get("materialized_memory_id")) for d in decisions),
            "simulation_kinds": sorted({str(s.get("simulation_kind")) for s in scenes}),
            "source_memory_ids": sorted({str(r.get("source_memory_id")) for r in bundle["replay_items"]}),
            "scene_hashes": [str(s.get("content_sha256")) for s in scenes],
            "integrity": integrity,
            "truth_boundary": (
                "This report proves only recorded runtime rest computation. Dream scenes are simulated internal content, "
                "not observed events, biological dreams, or factual memories."
            ),
        }
        generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
        report_id = uuid.uuid4().hex
        digest = self.store.save_wake_report(
            report_id=report_id,
            episode_id=episode_id,
            generated_at_utc=generated,
            report=report,
            validation_status="valid" if continuity is not RestContinuityStatus.REST_INTEGRITY_FAILED else "invalid",
        )
        return {**report, "report_id": report_id, "report_sha256": digest, "generated_at_utc": generated}

    def load_latest_verified(self) -> dict[str, Any]:
        row = self.store.latest_wake_report_row()
        if not row:
            return self._empty(RestContinuityStatus.REST_NONE, "report_missing")
        try:
            report = json.loads(str(row["report_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._empty(RestContinuityStatus.REST_INTEGRITY_FAILED, "report_json_invalid")
        digest = sha256_text(canonical_json(report))
        if digest != str(row["report_sha256"]) or row.get("validation_status") != "valid":
            return self._empty(RestContinuityStatus.REST_INTEGRITY_FAILED, "report_hash_or_validation_failed")
        return {**report, "report_id": row["report_id"], "report_sha256": digest, "generated_at_utc": row["generated_at_utc"]}

    @staticmethod
    def bounded_context(report: dict[str, Any]) -> dict[str, Any]:
        return {
            "rest_continuity_status": report.get("rest_continuity_status", RestContinuityStatus.REST_NONE.value),
            "episode_id": report.get("episode_id"),
            "cycle_count": int(report.get("cycle_count") or 0),
            "dream_scene_count": int(report.get("dream_scene_count") or 0),
            "materialized_l2_candidate_count": int(report.get("materialized_l2_candidate_count") or 0),
            "verified_process_elapsed_seconds": report.get("verified_process_elapsed_seconds"),
            "verified_idle_window_seconds": report.get("verified_idle_window_seconds"),
            "report_sha256": report.get("report_sha256"),
            "truth_boundary": report.get("truth_boundary"),
        }

    @staticmethod
    def _empty(status: RestContinuityStatus, reason: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "runtime_version": PACKAGE_VERSION_FULL,
            "rest_continuity_status": status.value,
            "reason": reason,
            "cycle_count": 0,
            "dream_scene_count": 0,
            "truth_boundary": "No verified rest activity may be claimed without a valid persisted report.",
        }


def load_latest_rest_wake_report(path: str | Path) -> dict[str, Any]:
    """Read the latest report without creating or mutating the rest database."""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        return RestWakeReportBuilder._empty(RestContinuityStatus.REST_NONE, "rest_store_missing")
    try:
        con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if "rest_wake_reports" not in tables:
                return RestWakeReportBuilder._empty(RestContinuityStatus.REST_NONE, "rest_report_table_missing")
            integrity = str(con.execute("PRAGMA quick_check").fetchone()[0])
            if integrity != "ok":
                return RestWakeReportBuilder._empty(RestContinuityStatus.REST_INTEGRITY_FAILED, f"rest_store_integrity={integrity}")
            row = con.execute("SELECT * FROM rest_wake_reports ORDER BY generated_at_utc DESC,rowid DESC LIMIT 1").fetchone()
        finally:
            con.close()
    except (sqlite3.DatabaseError, OSError) as exc:
        return RestWakeReportBuilder._empty(RestContinuityStatus.REST_INTEGRITY_FAILED, f"{type(exc).__name__}: {exc}")
    if row is None:
        return RestWakeReportBuilder._empty(RestContinuityStatus.REST_NONE, "report_missing")
    try:
        report = json.loads(str(row["report_json"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return RestWakeReportBuilder._empty(RestContinuityStatus.REST_INTEGRITY_FAILED, "report_json_invalid")
    digest = sha256_text(canonical_json(report))
    if digest != str(row["report_sha256"]) or str(row["validation_status"]) != "valid":
        return RestWakeReportBuilder._empty(RestContinuityStatus.REST_INTEGRITY_FAILED, "report_hash_or_validation_failed")
    return {**report, "report_id": row["report_id"], "report_sha256": digest, "generated_at_utc": row["generated_at_utc"]}
