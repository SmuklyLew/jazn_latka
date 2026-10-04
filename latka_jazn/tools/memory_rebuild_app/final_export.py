from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import os
import shutil
import uuid

from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.chat_export_reader import sha256_file
from latka_jazn.version import PACKAGE_VERSION_FULL

from .report_sanitizer import sanitize_report
from .test_profiles import run_test_profile
from .unified_memory import CANONICAL_DATABASE_NAME, UnifiedMemoryDatabase

EXPORT_SCHEMA = "jazn_unified_memory_export/v3.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_write(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _resolve_memory_evidence(memory_root: Path, raw: str | Path) -> Path:
    root = memory_root.expanduser().resolve()
    candidate = Path(raw).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"memory evidence must remain inside canonical memory root: {resolved}"
        ) from exc
    return resolved


def _publish_directory_atomically(
    staging: Path,
    target: Path,
    *,
    overwrite: bool,
) -> Path | None:
    """Publish staging and restore the old target if the final rename fails."""

    backup: Path | None = None
    if target.exists():
        if not overwrite:
            raise FileExistsError(target)
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = target.with_name(
            target.name + f".backup-{suffix}-{uuid.uuid4().hex[:8]}"
        )
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except BaseException:
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    return backup


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
    return {"schema_version": "jazn_unified_memory_sources/v3.0", "sources": items}


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
    with store.connect(read_only=True) as con:
        source_meta = {
            str(row[0]): str(row[1])
            for row in con.execute("SELECT key,value FROM unified_memory_meta")
        }
    memory_root = store.path.parent.parent.resolve()

    effective_baselines = list(baselines)
    if not effective_baselines:
        metadata_baseline = str(source_meta.get("test04_baseline_root") or "").strip()
        if metadata_baseline:
            effective_baselines.append(_resolve_memory_evidence(memory_root, metadata_baseline))
    effective_acceptance_report = acceptance_report
    if effective_acceptance_report is None:
        metadata_acceptance = str(
            source_meta.get("test04_acceptance_report") or ""
        ).strip()
        if metadata_acceptance:
            effective_acceptance_report = _resolve_memory_evidence(memory_root, metadata_acceptance)
    test_report = run_test_profile(
        store.path,
        "final",
        baselines=effective_baselines,
        full_validation=True,
        acceptance_report=effective_acceptance_report,
        system_acceptance=system_acceptance,
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
        with staged_store.connect() as con:
            meta_before = {
                str(row[0]): str(row[1])
                for row in con.execute("SELECT key,value FROM unified_memory_meta")
            }
            con.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('exported_from_generation',?)",
                (meta_before.get("memory_generation", ""),),
            )
            con.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('memory_generation','release')"
            )
            con.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('memory_readiness_class','native_unified')"
            )
            con.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('final_export_release',?)",
                (PACKAGE_VERSION_FULL,),
            )
            con.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('final_exported_at_utc',?)",
                (_utc_now(),),
            )
            con.commit()

        staged_validation = staged_store.validate(full=True)
        if not staged_validation["ok"]:
            raise RuntimeError("Walidacja stagingowego memory_jazn.sqlite3 nie powiodła się.")
        runtime_probe = probe_unified_memory_database(database_target, full_integrity=True)
        if not runtime_probe.get("full_autobiographical_recall_ready"):
            raise RuntimeError(
                "Finalny eksport nie przechodzi native unified runtime readiness probe."
            )

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
            unified_meta = {
                str(row[0]): str(row[1])
                for row in con.execute("SELECT key,value FROM unified_memory_meta")
            }

        database_manifest = {
            "schema_version": EXPORT_SCHEMA,
            "database": CANONICAL_DATABASE_NAME,
            "size_bytes": database_target.stat().st_size,
            "sha256": sha256_file(database_target),
            "schema_identity": runtime_probe.get("schema_identity"),
            "memory_generation": "release",
            "exported_from_generation": unified_meta.get("exported_from_generation") or None,
            "memory_readiness_class": "native_unified",
            "memory_search_ready": bool(runtime_probe.get("memory_search_ready")),
            "full_autobiographical_recall_ready": bool(
                runtime_probe.get("full_autobiographical_recall_ready")
            ),
            "restore_run_id": unified_meta.get("restore_run_id") or None,
            "protocol_run_id": unified_meta.get("protocol_run_id") or None,
            "parent_database_sha256": unified_meta.get("parent_database_sha256") or None,
            "test04_acceptance_report": unified_meta.get("test04_acceptance_report") or None,
            "test04_baseline_root": unified_meta.get("test04_baseline_root") or None,
            "source_union_sha256": unified_meta.get("source_union_sha256") or source_manifest_sha,
            "studio_release": PACKAGE_VERSION_FULL,
            "validation": staged_validation,
            "runtime_probe": runtime_probe,
        }
        _json_write(staging / "source-manifest.private.json", source_manifest)
        _json_write(staging / "source-manifest.sanitized.json", sanitize_report(source_manifest))
        _json_write(staging / "test-profile-final.private.json", test_report)
        _json_write(staging / "test-profile-final.sanitized.json", sanitize_report(test_report))
        _json_write(staging / "candidate-review-ledger.json", {
            "schema_version": "jazn_candidate_review_ledger/v3.0",
            "candidates": candidate_ledger,
            "revisions": candidate_revisions,
        })
        _json_write(staging / "promotion-ledger.json", {
            "schema_version": "jazn_promotion_ledger_export/v3.0",
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
            "source_union_sha256": database_manifest["source_union_sha256"],
            "schema_identity": database_manifest["schema_identity"],
            "memory_generation": "release",
            "memory_readiness_class": "native_unified",
            "full_autobiographical_recall_ready": True,
            "database_manifest": database_manifest,
            "automatic_l2": promotion_validation.get("automatic_l2"),
            "automatic_l3": promotion_validation.get("automatic_l3"),
            "promotion_ledger_verified": bool(promotion_validation.get("ok")),
            "runtime_activated": False,
        }
        _json_write(staging / "final-export-summary.json", summary)

        backup = _publish_directory_atomically(
            staging,
            target,
            overwrite=overwrite,
        )
        return {
            **summary,
            "output": str(target),
            "replaced_output_backup": str(backup) if backup is not None else None,
        }
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["EXPORT_SCHEMA", "export_final_memory"]
