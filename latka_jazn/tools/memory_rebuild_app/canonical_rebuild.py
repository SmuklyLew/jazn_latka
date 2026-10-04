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

from latka_jazn.tools.chat_export_reader import sha256_file
from latka_jazn.tools.memory_rebuild_common import MemoryRebuildPaths
from latka_jazn.tools.sqlite_archive_snapshot import create_sqlite_snapshot
from latka_jazn.version import PACKAGE_VERSION_FULL

from .application import resolve_base_commit
from .models import RebuildProject
from .protocol_engine import ProtocolEngine
from .test_profiles import baseline_record_reconciliation, semantic_database_fingerprint
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


def _is_commit_sha(value: str) -> bool:
    stripped = value.strip().lower()
    return len(stripped) == 40 and all(char in "0123456789abcdef" for char in stripped)


def _protocol_base_commit(tool_root: Path) -> str:
    try:
        commit = resolve_base_commit(tool_root)
    except RuntimeError:
        provenance = tool_root / "SOURCE_PROVENANCE.json"
        if not provenance.is_file():
            raise RuntimeError(
                "protocol_base_commit_unavailable: git and SOURCE_PROVENANCE.json are unavailable"
            )
        try:
            payload = json.loads(provenance.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"protocol_source_provenance_invalid: {exc}") from exc
        for key in ("source_commit", "base_merge_commit"):
            candidate = str(payload.get(key) or "").strip().lower()
            if _is_commit_sha(candidate):
                return candidate
        raise RuntimeError("protocol_source_provenance_has_no_valid_source_commit")
    if not _is_commit_sha(commit):
        raise RuntimeError("protocol_base_commit_invalid")
    return commit


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
        encoded = {
            json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            for item in canonical
        }
        canonical_union = [json.loads(item) for item in sorted(encoded)]
        payload = json.dumps(
            canonical_union,
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

        benchmark_raw = str(self.project.settings.get("test04_benchmark") or "").strip()
        benchmark = Path(benchmark_raw).expanduser().resolve() if benchmark_raw else None
        benchmark_sha256: str | None = None
        if benchmark is None:
            errors.append("test04_benchmark_missing")
        elif not benchmark.is_file():
            errors.append("test04_benchmark_missing")
        else:
            benchmark_sha256 = sha256_file(benchmark)

        system_acceptance = bool(self.project.settings.get("system_acceptance", False))
        restart_raw = str(self.project.settings.get("restart_continuity_report") or "").strip()
        restart_report = Path(restart_raw).expanduser().resolve() if restart_raw else None
        restart_report_sha256: str | None = None
        if system_acceptance and (restart_report is None or not restart_report.is_file()):
            errors.append("restart_continuity_report_missing")
        elif restart_report is not None and restart_report.is_file():
            restart_report_sha256 = sha256_file(restart_report)

        protocol_base_commit: str | None = None
        try:
            protocol_base_commit = _protocol_base_commit(self.tool_root)
        except RuntimeError as exc:
            errors.append(str(exc).split(":", 1)[0])

        existing = self._database_paths()
        existing_inventory = [
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in existing
        ]
        generation = "beta" if existing else "alpha"
        union_sha = self._source_union_sha256(inventory)
        protocol_gate = {
            "required": True,
            "protocol_order": ["test00", "test01", "test02", "test03", "test04", "final"],
            "test04_benchmark": str(benchmark) if benchmark is not None else None,
            "test04_benchmark_sha256": benchmark_sha256,
            "system_acceptance": system_acceptance,
            "restart_continuity_report": (
                str(restart_report) if restart_report is not None else None
            ),
            "restart_continuity_report_sha256": restart_report_sha256,
            "base_commit": protocol_base_commit,
        }
        payload = {
            "ok": not errors,
            "pipeline_owner": "UnifiedMemoryDatabase",
            "pipeline_schema": "jazn_memory_rebuild_studio_pipeline/v3",
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
            "existing_database_inventory": existing_inventory,
            "disk_preflight": disk,
            "protocol_gate": protocol_gate,
            "errors": errors,
            "automatic_experience_approval": False,
            "automatic_l2": False,
            "automatic_l3": False,
            "automatic_activation": False,
        }
        execution_contract = {
            "package_version": PACKAGE_VERSION_FULL,
            "canonical_database": payload["canonical_database"],
            "memory_generation": payload["memory_generation"],
            "source_inventory": [
                {
                    "path": item["path"],
                    "role": item["role"],
                    "pipeline": item["pipeline"],
                    "truth_domain": item["truth_domain"],
                    "source_family": item["source_family"],
                    "size_bytes": item["size_bytes"],
                    "sha256": item["sha256"],
                    "disposition": item["disposition"],
                    "disposition_reason": item["disposition_reason"],
                }
                for item in inventory
            ],
            "source_union_sha256": union_sha,
            "existing_database_inventory": existing_inventory,
            "protocol_gate": protocol_gate,
        }
        payload["execution_plan_sha256"] = hashlib.sha256(
            json.dumps(
                execution_contract,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        return payload

    def prepublish_runtime_gate(self) -> dict[str, Any]:
        """Re-check system runtime state immediately before replacing live DBs."""

        if self.project.mode != "system":
            return {
                "ok": True,
                "mode": self.project.mode,
                "status": "not_required_for_developer_target",
                "blocking_errors": [],
                "warnings": [],
                "evidence": {},
            }
        from latka_jazn.tools.memory_restore_types import (
            MemoryRestoreSettings,
            target_preflight,
        )

        settings = MemoryRestoreSettings(
            source_directory=self.project.source_directory,
            target_root=self.project.target_root,
            mode="system",
        )
        return target_preflight(settings, tool_root=self.tool_root)


    def _write_rebuild_metadata(
        self,
        store: UnifiedMemoryDatabase,
        *,
        plan: dict[str, Any],
        run_id: str,
        parent_database_sha256: str | None,
        readiness_class: str,
        protocol_run_id: str | None = None,
        acceptance_report: str | None = None,
        baseline_root: str | None = None,
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
            "protocol_run_id": protocol_run_id or "",
            "test04_acceptance_report": acceptance_report or "",
            "test04_baseline_root": baseline_root or "",
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
        expected_plan_sha = str(expected.get("execution_plan_sha256") or "")
        current_plan_sha = str(current.get("execution_plan_sha256") or "")
        if not expected_plan_sha or expected_plan_sha != current_plan_sha:
            return {
                "ok": False,
                "status": "prepared_plan_stale",
                "field": "execution_plan_sha256",
                "expected": expected_plan_sha or None,
                "actual": current_plan_sha or None,
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

            protocol_gate = dict(current.get("protocol_gate") or {})
            benchmark = Path(str(protocol_gate["test04_benchmark"])).expanduser().resolve()
            restart_report = protocol_gate.get("restart_continuity_report")
            protocol_engine = ProtocolEngine(
                baseline_root / "protocol",
                system_version=PACKAGE_VERSION_FULL,
                base_commit=str(protocol_gate["base_commit"]),
                run_id=f"restore-{run_id}",
            )
            rebuild_paths = [
                Path(item["path"])
                for item in current["source_inventory"]
                if item["pipeline"] == "memory_rebuild"
            ]
            test00 = protocol_engine.run_test00(rebuild_paths)
            if not test00.get("downstream_ready"):
                raise RuntimeError("protocol_test00_failed")
            test01 = protocol_engine.run_test01(
                rebuild_paths,
                test00_result=test00,
            )
            if not test01.get("ok"):
                raise RuntimeError("protocol_test01_failed")
            protocol_database = Path(str(test01["artifacts"]["database"]))
            test02 = protocol_engine.run_test02(
                protocol_database,
                test01_result=test01,
            )
            if not test02.get("ok"):
                raise RuntimeError("protocol_test02_failed")
            test03 = protocol_engine.run_test03(
                rebuild_paths,
                test02_result=test02,
            )
            if not test03.get("ok"):
                raise RuntimeError("protocol_test03_failed")
            staged = UnifiedMemoryDatabase(stage_database)
            initialized = staged.initialize()
            migration: dict[str, Any] = {"ok": True, "status": "not_required"}
            if snapshot_paths:
                migration = staged.migrate_databases(snapshot_paths, dry_run=False)
                if not migration.get("ok"):
                    raise RuntimeError("legacy_or_alpha_migration_failed")

            imported = staged.import_sources(rebuild_paths, full_validation=True)
            if not imported.get("ok"):
                raise RuntimeError("unified_source_import_failed")

            staged.rebuild_search_indexes()
            stable_stat_keys = (
                "conversations",
                "nodes",
                "fts_docs",
                "journal_entries",
                "candidates",
                "experiences",
                "memory_records",
                "memory_l0_records",
                "memory_l0_conversations",
                "import_sources",
            )
            idempotence_before_all = staged.stats()
            idempotence_before = {
                key: int(idempotence_before_all.get(key, 0))
                for key in stable_stat_keys
            }
            idempotence_import = staged.import_sources(
                rebuild_paths,
                full_validation=True,
            )
            staged.rebuild_search_indexes()
            idempotence_after_all = staged.stats()
            idempotence_after = {
                key: int(idempotence_after_all.get(key, 0))
                for key in stable_stat_keys
            }
            idempotence_report = {
                "ok": bool(idempotence_import.get("ok"))
                and idempotence_before == idempotence_after,
                "before": idempotence_before,
                "after": idempotence_after,
                "second_import": idempotence_import,
            }
            if not idempotence_report["ok"]:
                raise RuntimeError("same_target_idempotence_failed")
            self._write_rebuild_metadata(
                staged,
                plan=current,
                run_id=run_id,
                parent_database_sha256=parent_database_sha256,
                readiness_class="candidate_native_unified",
                protocol_run_id=protocol_engine.run_id,
            )
            validation = staged.validate(full=True)
            if not validation.get("ok"):
                raise RuntimeError("staged_unified_validation_failed")
            baseline_reconciliation = (
                baseline_record_reconciliation(stage_database, snapshot_paths)
                if snapshot_paths
                else {"ok": True, "status": "not_applicable", "tables": {}}
            )
            if not baseline_reconciliation.get("ok"):
                raise RuntimeError("alpha_or_legacy_baseline_reconciliation_failed")
            from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database

            staged_probe = probe_unified_memory_database(stage_database, full_integrity=True)
            if not staged_probe.get("full_autobiographical_recall_ready"):
                raise RuntimeError("staged_runtime_readiness_probe_failed")

            # Test04 and Final belong to the exact staged candidate.  Test03
            # establishes deterministic source reconstruction; the explicit
            # reconciliation below is the verified transition to the
            # migration-aware alpha/beta candidate.
            test04 = protocol_engine.run_test04(
                stage_database,
                benchmark,
                test03_result=test03,
                candidate_reconciliation=baseline_reconciliation,
                system_acceptance=bool(protocol_gate.get("system_acceptance")),
                restart_continuity_report=restart_report,
            )
            if not test04.get("ok"):
                raise RuntimeError("protocol_candidate_test04_failed")
            candidate_test04_validation = dict(
                (test04.get("details") or {}).get("validation") or {}
            )
            if not candidate_test04_validation.get("ok"):
                raise RuntimeError("protocol_candidate_test04_validation_failed")

            protocol_final_output = baseline_root / "protocol-final"
            final_protocol = protocol_engine.run_final(
                stage_database,
                protocol_final_output,
                test04_result=test04,
                sources=rebuild_paths,
            )
            if not final_protocol.get("ok"):
                raise RuntimeError("protocol_final_failed")
            protocol_manifest = protocol_engine.seal_manifest()
            protocol_report = {
                "ok": True,
                "run_id": protocol_engine.run_id,
                "test00": test00.get("outcome"),
                "test01": test01.get("outcome"),
                "test02": test02.get("outcome"),
                "test03": test03.get("outcome"),
                "test04": test04.get("outcome"),
                "final": final_protocol.get("outcome"),
                "test04_candidate_transition": (
                    (test04.get("artifacts") or {}).get("candidate_transition")
                ),
                "test04_database_sha256": (
                    (test04.get("artifacts") or {}).get("database_sha256")
                ),
                "test04_database_fingerprint": (
                    (test04.get("artifacts") or {}).get("database_fingerprint")
                ),
                "source_union_fingerprint": (
                    final_protocol.get("artifacts") or {}
                ).get("source_union_fingerprint"),
                "manifest": protocol_manifest,
                "final_output": str(protocol_final_output),
            }
            candidate_semantic_fingerprint = semantic_database_fingerprint(stage_database)

            test04_checks = {
                str(item.get("name")): bool(item.get("passed"))
                for item in candidate_test04_validation.get("checks", [])
                if isinstance(item, dict)
            }
            protocol_test03_details = test03.get("details") or {}
            acceptance_baseline = (
                str(baseline_sqlite)
                if snapshot_paths
                else str(protocol_final_output)
            )
            compatibility_acceptance = {
                "schema_version": "jazn_memory_rebuild_acceptance/v3.1",
                "generated_from": "ProtocolEngine+CanonicalMemoryRebuildPipeline",
                "run_id": run_id,
                "protocol_run_id": protocol_engine.run_id,
                "binding": {
                    "database_semantic_fingerprint": candidate_semantic_fingerprint,
                    "source_union_sha256": current["source_union_sha256"],
                    "restore_run_id": run_id,
                    "protocol_run_id": protocol_engine.run_id,
                },
                "final": {
                    "structural_integrity": "passed",
                    "source_completeness": (
                        "passed" if test00.get("downstream_ready") else "failed"
                    ),
                    "same_target_idempotence": (
                        "passed" if idempotence_report["ok"] else "failed"
                    ),
                    "fresh_rebuild_reproducibility": (
                        "passed"
                        if bool(protocol_test03_details.get("semantic_reconciliation"))
                        else "failed"
                    ),
                    "test03_reconciliation": (
                        "passed" if baseline_reconciliation.get("ok") else "failed"
                    ),
                    "recall": (
                        "passed" if candidate_test04_validation.get("ok") else "failed"
                    ),
                    "multi_turn_review": (
                        "passed"
                        if test04_checks.get("referential_multi_turn_context")
                        else "failed"
                    ),
                    "html_import_dry_run": "not_applicable",
                    "restart_continuity": (
                        "passed"
                        if bool(protocol_gate.get("system_acceptance"))
                        and test04_checks.get("restart_continuity")
                        else "not_run"
                    ),
                },
                "evidence": {
                    "source_union_sha256": current["source_union_sha256"],
                    "protocol_source_union_fingerprint": protocol_report.get(
                        "source_union_fingerprint"
                    ),
                    "baseline_reconciliation": baseline_reconciliation,
                    "same_target_idempotence": idempotence_report,
                    "runtime_probe_status": staged_probe.get("status"),
                    "schema_identity": staged_probe.get("schema_identity"),
                    "candidate_database_semantic_fingerprint": (
                        candidate_semantic_fingerprint
                    ),
                    "candidate_test04_validation": candidate_test04_validation,
                },
            }
            acceptance_path = baseline_root / "test04-acceptance.private.json"
            _atomic_json(acceptance_path, compatibility_acceptance)
            acceptance_relative = acceptance_path.relative_to(memory_root).as_posix()
            acceptance_baseline_path = Path(acceptance_baseline).expanduser().resolve()
            baseline_relative = acceptance_baseline_path.relative_to(memory_root).as_posix()
            self._write_rebuild_metadata(
                staged,
                plan=current,
                run_id=run_id,
                parent_database_sha256=parent_database_sha256,
                readiness_class="native_unified",
                protocol_run_id=protocol_engine.run_id,
                acceptance_report=acceptance_relative,
                baseline_root=baseline_relative,
            )
            staged.checkpoint()
            if semantic_database_fingerprint(stage_database) != candidate_semantic_fingerprint:
                raise RuntimeError("candidate_changed_after_test04_acceptance")

            publish_runtime_gate = self.prepublish_runtime_gate()
            if not publish_runtime_gate.get("ok") or publish_runtime_gate.get(
                "blocking_errors"
            ):
                raise RuntimeError("system_runtime_became_active_before_publish")

            self.paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
            rollback_dir.mkdir(parents=True, exist_ok=True)
            moved: list[tuple[Path, Path]] = []
            active_files: list[Path] = []
            for database_path in existing:
                for item in self._sidecars(database_path):
                    if item.exists():
                        active_files.append(item)
            published = False
            try:
                for original in active_files:
                    backup = rollback_dir / original.name
                    if backup.exists():
                        backup = rollback_dir / f"{uuid.uuid4().hex}-{original.name}"
                    os.replace(original, backup)
                    moved.append((original, backup))

                os.replace(stage_database, self.database)
                published = True
                final_store = UnifiedMemoryDatabase(self.database)
                final_validation = final_store.validate(full=True)
                final_probe = probe_unified_memory_database(self.database, full_integrity=True)
                if not final_validation.get("ok"):
                    raise RuntimeError("published_unified_validation_failed")
                if not final_probe.get("full_autobiographical_recall_ready"):
                    raise RuntimeError("published_runtime_readiness_probe_failed")
            except BaseException:
                if published:
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
                "protocol_gate": protocol_report,
                "same_target_idempotence": idempotence_report,
                "baseline_reconciliation": baseline_reconciliation,
                "test04_acceptance_report": str(acceptance_path),
                "test04_baseline_root": acceptance_baseline,
                "candidate_database_semantic_fingerprint": (
                    candidate_semantic_fingerprint
                ),
                "candidate_test04_validation": candidate_test04_validation,
                "validation": final_validation,
                "runtime_probe": final_probe,
                "disk_preflight": current["disk_preflight"],
                "publish_runtime_gate": publish_runtime_gate,
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
