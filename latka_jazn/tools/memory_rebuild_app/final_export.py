from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import os
import shutil
import uuid

from latka_jazn.tools.chat_export_reader import sha256_file

from .report_sanitizer import sanitize_report
from .test_profiles import run_test_profile
from .unified_memory import CANONICAL_DATABASE_NAME, UnifiedMemoryDatabase

EXPORT_SCHEMA = "jazn_unified_memory_export/v2.4"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_write(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _source_manifest(sources: Iterable[str | Path]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for raw in sources:
        path = Path(raw).expanduser().resolve()
        items.append({
            "path": str(path),
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256_file(path) if path.is_file() else None,
        })
    return {"schema_version": "jazn_unified_memory_sources/v2.4", "sources": items}


def export_final_memory(
    database: str | Path,
    output: str | Path,
    *,
    baselines: Iterable[str | Path] = (),
    sources: Iterable[str | Path] = (),
    overwrite: bool = False,
    acceptance_report: str | Path | None = None,
    system_acceptance: bool = False,
) -> dict[str, Any]:
    store = UnifiedMemoryDatabase(database)
    test_report = run_test_profile(
        store.path, "final", baselines=baselines, full_validation=True,
        acceptance_report=acceptance_report, system_acceptance=system_acceptance,
    )
    if not test_report["ok"]:
        return {"ok": False, "status": "blocked_by_final_profile", "test_report": test_report}

    target = Path(output).expanduser().resolve()
    staging = target.with_name(target.name + f".staging-{uuid.uuid4().hex}")
    staging.mkdir(parents=True, exist_ok=False)
    started = _utc_now()
    try:
        database_target = staging / CANONICAL_DATABASE_NAME
        store.backup(database_target)
        staged_store = UnifiedMemoryDatabase(database_target)
        staged_validation = staged_store.validate(full=True)
        if not staged_validation["ok"]:
            raise RuntimeError("Walidacja stagingowego memory_jazn.sqlite3 nie powiodła się.")

        source_manifest = _source_manifest(sources)
        source_manifest_sha = hashlib.sha256(
            json.dumps(source_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with staged_store.connect(read_only=True) as con:
            candidate_ledger = [dict(row) for row in con.execute(
                "SELECT candidate_id,status,reviewed_at_utc,reviewed_by,review_reason FROM candidates ORDER BY candidate_id"
            ).fetchall()]
            candidate_revisions = [dict(row) for row in con.execute(
                "SELECT * FROM candidate_revisions ORDER BY candidate_id,revision"
            ).fetchall()]
            promotion_ledger = [dict(row) for row in con.execute(
                "SELECT * FROM promotion_ledger ORDER BY event_at_utc,ledger_id"
            ).fetchall()]

        database_manifest = {
            "schema_version": EXPORT_SCHEMA,
            "database": CANONICAL_DATABASE_NAME,
            "size_bytes": database_target.stat().st_size,
            "sha256": sha256_file(database_target),
            "validation": staged_validation,
        }
        _json_write(staging / "source-manifest.private.json", source_manifest)
        _json_write(staging / "source-manifest.sanitized.json", sanitize_report(source_manifest))
        _json_write(staging / "test-profile-final.private.json", test_report)
        _json_write(staging / "test-profile-final.sanitized.json", sanitize_report(test_report))
        _json_write(staging / "candidate-review-ledger.json", {
            "schema_version": "jazn_candidate_review_ledger/v2.4",
            "candidates": candidate_ledger,
            "revisions": candidate_revisions,
        })
        _json_write(staging / "promotion-ledger.json", {
            "schema_version": "jazn_promotion_ledger_export/v2.4",
            "entries": promotion_ledger,
        })
        _json_write(staging / "database-manifest.json", database_manifest)
        promotion_validation = test_report.get("promotion_ledger_validation") or {}
        summary = {
            "schema_version": EXPORT_SCHEMA,
            "ok": True,
            "status": "ready",
            "started_at_utc": started,
            "completed_at_utc": _utc_now(),
            "source_manifest_sha256": source_manifest_sha,
            "database_manifest": database_manifest,
            "automatic_l2": promotion_validation.get("automatic_l2"),
            "automatic_l3": promotion_validation.get("automatic_l3"),
            "promotion_ledger_verified": bool(promotion_validation.get("ok")),
            "runtime_activated": False,
        }
        _json_write(staging / "final-export-summary.json", summary)

        if target.exists():
            if not overwrite:
                raise FileExistsError(target)
            backup = target.with_name(target.name + ".backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            os.replace(target, backup)
        os.replace(staging, target)
        return {**summary, "output": str(target)}
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["EXPORT_SCHEMA", "export_final_memory"]
