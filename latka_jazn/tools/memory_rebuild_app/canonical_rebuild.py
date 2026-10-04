from __future__ import annotations

"""Canonical reconstruction pipeline for Jaźń Memory Rebuild Studio.

The Studio has one writable rebuild path: build a fresh unified database in
staging, preserve every pre-existing SQLite store as an immutable baseline,
validate the staged database with the runtime-native probe, then publish it
atomically to memory/sqlite/memory_jazn.sqlite3.

Legacy multi-database restore remains available through dedicated compatibility
tools, but it is never the default Studio rebuild owner.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import shutil
import uuid

from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.chat_export_reader import sha256_file
from latka_jazn.tools.memory_rebuild_common import MemoryRebuildPaths
from latka_jazn.tools.sqlite_archive_snapshot import create_sqlite_snapshot
from latka_jazn.version import PACKAGE_VERSION_FULL

from .models import RebuildProject
from .unified_memory import CANONICAL_DATABASE_NAME, UnifiedMemoryDatabase


_STAGING_RESERVE_BYTES = 512 * 1024 * 1024
_DISK_MARGIN_NUMERATOR = 120
_DISK_MARGIN_DENOMINATOR = 100


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]


def canonical_database_path(target_root: str | Path) -> Path:
    return MemoryRebuildPaths.from_root(target_root).memory_jazn


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _source_disposition(pipeline: str) -> tuple[str, str]:
    if pipeline == "memory_rebuild":
        return "imported_to_L0", "canonical_unified_import"
    if pipeline in {"html_control", "catalog_only", "sqlite_baseline"}:
        return "cold_evidence_only", f"pipeline:{pipeline}"
    return "excluded_with_reason", f"pipeline:{pipeline}"


class CanonicalMemoryRebuildPipeline:
    """Fail-closed Studio rebuild owner backed by UnifiedMemoryDatabase."""

    def __init__(self, project: RebuildProject, *, tool_root: str | Path | None = None) -> None:
        self.project = project.normalized()
        self.tool_root = Path(tool_root).expanduser().resolve() if tool_root else Path.cwd().resolve()
        self.target_root = Path(self.project.target_root).expanduser().resolve()
        self.paths = MemoryRebuildPaths.from_root(self.target_root)
        self.database = self.paths.memory_jazn

    def _database_paths(self) -> list[Path]:
        result: list[Path] = []
        seen: set[str] = set()
        for key in ("archive_chats", "journal", "memory_jazn", "experience", "import_catalog"):
            path = Path(getattr(self.paths, key)).resolve()
            norm = os.path.normcase(str(path))
            if norm in seen or not path.is_file():
                continue
            seen.add(norm)
            result.append(path)
        return result

    def _source_inventory(self) -> tuple[list[dict[str, Any]], list[str]]:
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        for source in self.project.enabled_sources():
            path = Path(source.path).expanduser().resolve()
            if not path.is_file():
                errors.append(f"source_missing:{source.source_id}")
                current_sha = None
                size = None
            else:
                size = path.stat().st_size
                current_sha = sha256_file(path)
                if source.sha256 and source.sha256 != current_sha:
                    errors.append(f"source_sha256_changed:{source.source_id}")
            disposition, reason = _source_disposition(source.pipeline)
            items.append(
                {
                    "source_id": source.source_id,
                    "path": str(path),
                    "role": source.role,
                    "pipeline": source.pipeline,
                    "truth_domain": source.truth_domain,
                    "source_family": source.source_family,
                    "size_bytes": size,
                    "sha256": current_sha,
                    "project_sha256": source.sha256,
                    "disposition": disposition,
                    "disposition_reason": reason,
                }
            )
        return items, errors

    @staticmethod
    def _source_union_sha256(items: list[dict[str, Any]]) -> str:
        canonical = [
            {
                "source_id": item["source_id"],
                "role": item["role"],
                "pipeline": item["pipeline"],
                "truth_domain": item["truth_domain"],
                "source_family": item["source_family"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
                "disposition": item["disposition"],
                "disposition_reason": item["disposition_reason"],
            }
            for item in items
        ]
        payload = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def disk_preflight(self, source_inventory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        inventory = source_inventory
        if inventory is None:
            inventory, _ = self._source_inventory()
        source_bytes = sum(int(item.get("size_bytes") or 0) for item in inventory)
        existing = self._database_paths()
        existing_bytes = sum(path.stat().st_size for path in existing)
        estimated_working = source_bytes + (existing_bytes * 3) + _STAGING_RESERVE_BYTES
        required = (estimated_working * _DISK_MARGIN_NUMERATOR) // _DISK_MARGIN_DENOMINATOR
        probe_root = _nearest_existing_parent(self.paths.sqlite_dir)
        usage = shutil.disk_usage(probe_root)
        return {
            "ok": usage.free >= required,
            "probe_root": str(probe_root),
            "source_bytes": source_bytes,
            "existing_database_bytes": existing_bytes,
            "staging_reserve_bytes": _STAGING_RESERVE_BYTES,
            "safety_margin_percent": 20,
            "required_free_bytes": required,
            "available_free_bytes": usage.free,
            "shortfall_bytes": max(0, required - usage.free),
        }

    def plan(self) -> dict[str, Any]:
        inventory, source_errors = self._source_inventory()
        rebuild = [item for item in inventory if item["pipeline"] == "memory_rebuild"]
        rejected = [
            {
                "path": item["path"],
                "source_id": item["source_id"],
                "reason": item["disposition_reason"],
            }
            for item in inventory
            if item["pipeline"] != "memory_rebuild"
        ]
        disk = self.disk_preflight(inventory)
        errors = list(source_errors)
        if not rebuild:
            errors.append("no_memory_rebuild_sources")
        if not disk["ok"]:
            errors.append("insufficient_disk_space")
        existing = self._database_paths()
        generation = "beta" if existing else "alpha"
        union_sha = self._source_union_sha256(inventory)
        return {
            "ok": not errors,
            "pipeline_owner": "UnifiedMemoryDatabase",
            "pipeline_schema": "jazn_memory_rebuild_studio_pipeline/v2",
            "canonical_database": str(self.database),
            "memory_generation": generation,
            "selected_source_count": len(rebuild),
            "chat_source_count": sum(
                1 for item in rebuild if item["role"] in {"chatgpt_export", "chatgpt_html_export"}
            ),
            "journal_source_count": sum(1 for item in rebuild if item["role"] == "journal"),
            "rejected_source_count": len(rejected),
            "rejected": rejected,
            "source_inventory": inventory,
            "source_union_sha256": union_sha,
            "existing_database_count": len(existing),
            "existing_databases": [str(path) for path in existing],
            "disk_preflight": disk,
            "errors": errors,
            "automatic_experience_approval": False,
            "automatic_l2": False,
            "automatic_l3": False,
            "automatic_activation": False,
        }

    def _write_rebuild_metadata(
        self,
        store: UnifiedMemoryDatabase,
        *,
        plan: dict[str, Any],
        run_id: str,
        parent_database_sha256: str | None,
        readiness_class: str,
    ) -> None:
        source_status = [
            {
                "source_id": item["source_id"],
                "sha256": item["sha256"],
                "role": item["role"],
                "pipeline": item["pipeline"],
                "disposition": item["disposition"],
                "reason": item["disposition_reason"],
            }
            for item in plan["source_inventory"]
        ]
        values = {
            "memory_generation": plan["memory_generation"],
            "restore_run_id": run_id,
            "parent_database_sha256": parent_database_sha256 or "",
            "source_union_sha256": plan["source_union_sha256"],
            "memory_readiness_class": readiness_class,
            "studio_release": PACKAGE_VERSION_FULL,
            "source_restore_status_json": json.dumps(
                source_status,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "reconstructed_at_utc": _utc_now(),
        }
        with store.connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES(?,?)",
                list(values.items()),
            )
            con.commit()

    @staticmethod
    def _sidecars(path: Path) -> list[Path]:
        return [
            path,
            Path(str(path) + "-wal"),
            Path(str(path) + "-shm"),
        ]

    def _restore_rollbacks(self, rollback_dir: Path, moved: list[tuple[Path, Path]]) -> None:
        for original, backup in reversed(moved):
            if not backup.exists():
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            os.replace(backup, original)
        shutil.rmtree(rollback_dir, ignore_errors=True)

    def run(self, *, prepared_plan: dict[str, Any] | None = None) -> dict[str, Any]:
        expected = prepared_plan or self.plan()
        if "engine_plan" in expected:
            expected = dict(expected["engine_plan"])
        current = self.plan()
        if not current["ok"]:
            return {"ok": False, "status": "rebuild_plan_blocked", "plan": current}
        for field in ("canonical_database", "source_union_sha256"):
            if expected.get(field) and expected.get(field) != current.get(field):
                return {
                    "ok": False,
                    "status": "prepared_plan_stale",
                    "field": field,
                    "expected": expected.get(field),
                    "actual": current.get(field),
                }

        run_id = _run_id()
        memory_root = self.paths.sqlite_dir.parent
        staging_root = memory_root / ".rebuild_staging" / run_id
        staging_sqlite = staging_root / "sqlite"
        stage_database = staging_sqlite / CANONICAL_DATABASE_NAME
        rollback_dir = staging_root / "rollback"
        baseline_root = memory_root / "rebuild_baselines" / run_id
        baseline_sqlite = baseline_root / "sqlite"
        staging_sqlite.mkdir(parents=True, exist_ok=False)
        baseline_sqlite.mkdir(parents=True, exist_ok=False)

        snapshot_reports: list[dict[str, Any]] = []
        snapshot_paths: list[Path] = []
        parent_database_sha256: str | None = None
        existing = self._database_paths()
        try:
            for source in existing:
                destination = baseline_sqlite / source.name
                source_file_sha256 = sha256_file(source)
                report = create_sqlite_snapshot(
                    source,
                    destination,
                    full_integrity_check=True,
                ).to_dict()
                report["source_file_sha256"] = source_file_sha256
                report["baseline_role"] = (
                    "alpha_parent" if source.resolve() == self.database.resolve() else "legacy_sibling"
                )
                snapshot_reports.append(report)
                snapshot_paths.append(destination)
                if source.resolve() == self.database.resolve():
                    parent_database_sha256 = str(report["snapshot_sha256"])

            _atomic_json(
                baseline_root / "baseline-manifest.json",
                {
                    "schema_version": "jazn_memory_rebuild_baseline/v1",
                    "immutable": True,
                    "run_id": run_id,
                    "created_at_utc": _utc_now(),
                    "memory_generation": current["memory_generation"],
                    "canonical_database": str(self.database),
                    "source_union_sha256": current["source_union_sha256"],
                    "snapshots": snapshot_reports,
                },
            )

            staged = UnifiedMemoryDatabase(stage_database)
            initialized = staged.initialize()
            migration: dict[str, Any] = {"ok": True, "status": "not_required"}
            if snapshot_paths:
                migration = staged.migrate_databases(snapshot_paths, dry_run=False)
                if not migration.get("ok"):
                    raise RuntimeError("legacy_or_alpha_migration_failed")

            rebuild_paths = [
                Path(item["path"])
                for item in current["source_inventory"]
                if item["pipeline"] == "memory_rebuild"
            ]
            imported = staged.import_sources(rebuild_paths, full_validation=True)
            if not imported.get("ok"):
                raise RuntimeError("unified_source_import_failed")

            staged.rebuild_search_indexes()
            self._write_rebuild_metadata(
                staged,
                plan=current,
                run_id=run_id,
                parent_database_sha256=parent_database_sha256,
                readiness_class="candidate_native_unified",
            )
            validation = staged.validate(full=True)
            if not validation.get("ok"):
                raise RuntimeError("staged_unified_validation_failed")
            staged_probe = probe_unified_memory_database(stage_database, full_integrity=True)
            if not staged_probe.get("full_autobiographical_recall_ready"):
                raise RuntimeError("staged_runtime_readiness_probe_failed")
            self._write_rebuild_metadata(
                staged,
                plan=current,
                run_id=run_id,
                parent_database_sha256=parent_database_sha256,
                readiness_class="native_unified",
            )
            staged.checkpoint()

            self.paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
            rollback_dir.mkdir(parents=True, exist_ok=True)
            moved: list[tuple[Path, Path]] = []
            active_files: list[Path] = []
            for database_path in existing:
                for item in self._sidecars(database_path):
                    if item.exists():
                        active_files.append(item)
            for original in active_files:
                backup = rollback_dir / original.name
                if backup.exists():
                    backup = rollback_dir / f"{uuid.uuid4().hex}-{original.name}"
                os.replace(original, backup)
                moved.append((original, backup))

            try:
                os.replace(stage_database, self.database)
                final_store = UnifiedMemoryDatabase(self.database)
                final_validation = final_store.validate(full=True)
                final_probe = probe_unified_memory_database(self.database, full_integrity=True)
                if not final_validation.get("ok"):
                    raise RuntimeError("published_unified_validation_failed")
                if not final_probe.get("full_autobiographical_recall_ready"):
                    raise RuntimeError("published_runtime_readiness_probe_failed")
            except BaseException:
                self.database.unlink(missing_ok=True)
                self._restore_rollbacks(rollback_dir, moved)
                raise

            shutil.rmtree(rollback_dir, ignore_errors=True)
            result = {
                "ok": True,
                "status": "native_unified_published",
                "pipeline_owner": "UnifiedMemoryDatabase",
                "run_id": run_id,
                "memory_generation": current["memory_generation"],
                "database": str(self.database),
                "schema_identity": final_probe.get("schema_identity"),
                "memory_readiness_class": "native_unified",
                "memory_search_ready": final_probe.get("memory_search_ready"),
                "full_autobiographical_recall_ready": final_probe.get(
                    "full_autobiographical_recall_ready"
                ),
                "source_union_sha256": current["source_union_sha256"],
                "parent_database_sha256": parent_database_sha256,
                "baseline_root": str(baseline_root),
                "baseline_snapshot_count": len(snapshot_reports),
                "migration": migration,
                "import": imported,
                "validation": final_validation,
                "runtime_probe": final_probe,
                "disk_preflight": current["disk_preflight"],
                "automatic_experience_approval": False,
                "automatic_l2": False,
                "automatic_l3": False,
                "automatic_activation": False,
            }
            _atomic_json(baseline_root / "rebuild-result.json", result)
            return result
        except BaseException as exc:
            failure = {
                "ok": False,
                "status": "canonical_rebuild_failed",
                "run_id": run_id,
                "database": str(self.database),
                "baseline_root": str(baseline_root),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "source_union_sha256": current.get("source_union_sha256"),
                "automatic_l2": False,
                "automatic_l3": False,
                "automatic_activation": False,
            }
            _atomic_json(baseline_root / "rebuild-failure.json", failure)
            return failure
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)


__all__ = ["CanonicalMemoryRebuildPipeline", "canonical_database_path"]
