from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json
import os
import re

from latka_jazn.tools.memory_restore import (
    MemoryRestoreOrchestrator,
    MemoryRestorePlan,
    MemoryRestoreSettings,
    confirmation_token,
)

from .baseline_registry import baseline_from_path, refresh_baseline
from .models import BaselineSpec, RebuildProject, SourceSpec, utc_iso
from .project_store import ProjectStore
from .source_inventory import inspect_source
from .sqlite_inspector import compare_database_summaries, inspect_database_set

_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[._-](0[1-9]|1[0-2])[._-](0[1-9]|[12]\d|3[01])(?!\d)")


class MemoryRebuildAppError(RuntimeError):
    pass


class MemoryRebuildAppController:
    def __init__(
        self,
        project: RebuildProject,
        *,
        store: ProjectStore | None = None,
        tool_root: str | Path | None = None,
        callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.project = project.normalized()
        self.store = store or ProjectStore()
        self.tool_root = Path(tool_root).expanduser().resolve() if tool_root else Path.cwd().resolve()
        self.callback = callback

    def save(self) -> Path:
        return self.store.save(self.project)

    def settings(self) -> MemoryRestoreSettings:
        values = self.project.settings
        mode = self.project.mode
        if mode not in ("developer", "system"):
            raise ValueError(f"unsupported restore mode: {mode}")
        return MemoryRestoreSettings(
            source_directory=self.project.source_directory,
            target_root=self.project.target_root,
            mode=mode,
            recursive_scan=bool(values.get("recursive_scan", False)),
            verify_after_each=bool(values.get("verify_after_each", True)),
            full_validation=bool(values.get("full_validation", True)),
            continue_on_error=bool(values.get("continue_on_error", False)),
            create_backup=bool(values.get("create_backup", True)),
            audit_classifiers=bool(values.get("audit_classifiers", True)),
            reclassify_journal_dry_run=bool(values.get("reclassify_journal_dry_run", True)),
            apply_reclassification=bool(values.get("apply_reclassification", False)),
            analyse_topics=bool(values.get("analyse_topics", False)),
            force_topics=bool(values.get("force_topics", False)),
            candidate_limit=max(0, int(values.get("candidate_limit", 0))),
            progress_every_conversations=max(1, int(values.get("progress_every_conversations", 5))),
            baseline_roots=[item.path for item in self.project.enabled_baselines()],
        ).normalized()

    def inspect_and_add_source(
        self,
        path: str | Path,
        *,
        approved: bool = False,
        calculate_sha256: bool | None = None,
        verify_zip_crc: bool | None = None,
    ) -> SourceSpec:
        calculate_sha256 = (
            bool(self.project.settings.get("hash_sources_during_scan", True))
            if calculate_sha256 is None
            else bool(calculate_sha256)
        )
        verify_zip_crc = (
            bool(self.project.settings.get("verify_zip_crc_during_scan", False))
            if verify_zip_crc is None
            else bool(verify_zip_crc)
        )
        inspection = inspect_source(
            path,
            calculate_sha256=calculate_sha256,
            verify_zip_crc=verify_zip_crc,
        )
        source = inspection.to_source_spec(approved=approved)
        return self.project.add_source(source)

    def refresh_source(self, source_id: str) -> SourceSpec:
        source = self.project.source_by_id(source_id)
        inspection = inspect_source(
            source.path,
            calculate_sha256=bool(self.project.settings.get("hash_sources_during_scan", True)),
            verify_zip_crc=bool(self.project.settings.get("verify_zip_crc_during_scan", False)),
        )
        source.size_bytes = inspection.size_bytes
        source.sha256 = inspection.sha256
        source.status = inspection.status
        source.warnings = inspection.warnings
        source.metadata = inspection.metadata
        if source.role == "unknown":
            source.role = inspection.role
        if source.truth_domain == "unknown":
            source.truth_domain = inspection.truth_domain
        if source.pipeline in {"catalog_only", "excluded"} and inspection.pipeline not in {"catalog_only", "excluded"}:
            source.pipeline = inspection.pipeline
        if not source.source_family:
            source.source_family = inspection.source_family
        self.project.touch()
        return source

    def add_baseline(
        self,
        path: str | Path,
        *,
        label: str | None = None,
        full_integrity: bool = False,
    ) -> BaselineSpec:
        baseline = baseline_from_path(
            path,
            label=label,
            full_integrity=full_integrity,
            calculate_sha256=True,
        )
        return self.project.add_baseline(baseline)

    def refresh_baselines(self, *, full_integrity: bool = False) -> list[BaselineSpec]:
        for baseline in self.project.baselines:
            refresh_baseline(baseline, full_integrity=full_integrity, calculate_sha256=True)
        self.project.touch()
        return list(self.project.baselines)

    def preflight(self) -> dict[str, Any]:
        enabled = self.project.enabled_sources()
        missing = [item.path for item in enabled if not Path(item.path).is_file()]
        blocked = [
            {"source_id": item.source_id, "path": item.path, "warnings": item.warnings}
            for item in enabled
            if any(str(warning).startswith("blocking:") for warning in item.warnings)
        ]
        duplicate_hashes: list[dict[str, Any]] = []
        by_hash: dict[str, list[SourceSpec]] = {}
        for source in enabled:
            if source.sha256:
                by_hash.setdefault(source.sha256, []).append(source)
        for digest, sources in by_hash.items():
            if len(sources) > 1:
                duplicate_hashes.append(
                    {"sha256": digest, "sources": [item.path for item in sources]}
                )

        rebuild_sources = [item for item in enabled if item.pipeline == "memory_rebuild"]
        journal_positions = [index for index, item in enumerate(rebuild_sources) if item.role == "journal"]
        order_warnings: list[str] = []
        if journal_positions and journal_positions[-1] != len(rebuild_sources) - 1:
            order_warnings.append("journal_should_be_last_memory_rebuild_source")
        if any(item.role == "chatgpt_html_export" and item.pipeline == "memory_rebuild" for item in enabled):
            order_warnings.append("html_should_use_html_control_pipeline")

        target = Path(self.project.target_root) if self.project.target_root else None
        target_exists = bool(target and target.exists())
        target_inside_repo = False
        if target:
            try:
                target.resolve().relative_to(self.tool_root)
                target_inside_repo = True
            except ValueError:
                pass

        errors: list[str] = []
        if not self.project.target_root:
            errors.append("target_root_missing")
        if missing:
            errors.append("enabled_sources_missing")
        if blocked:
            errors.append("enabled_sources_blocked")
        if not rebuild_sources:
            errors.append("no_memory_rebuild_sources")
        if self.project.mode == "developer" and target_inside_repo:
            errors.append("developer_target_inside_repository")

        return {
            "ok": not errors,
            "errors": errors,
            "warnings": order_warnings,
            "enabled_source_count": len(enabled),
            "memory_rebuild_source_count": len(rebuild_sources),
            "catalog_only_source_count": sum(1 for item in enabled if item.pipeline == "catalog_only"),
            "html_control_source_count": sum(1 for item in enabled if item.pipeline == "html_control"),
            "missing_sources": missing,
            "blocked_sources": blocked,
            "duplicate_hash_groups": duplicate_hashes,
            "target_root": self.project.target_root,
            "target_exists": target_exists,
            "target_inside_repository": target_inside_repo,
            "automatic_experience_approval": False,
            "automatic_l2": False,
            "automatic_l3": False,
        }

    def _orchestrator(self) -> MemoryRestoreOrchestrator:
        return MemoryRestoreOrchestrator(
            self.settings(),
            tool_root=self.tool_root,
            callback=self.callback,
        )

    def _rebuild_paths(self) -> list[Path]:
        return [Path(item.path) for item in self.project.enabled_sources(pipeline="memory_rebuild")]

    def plan(self) -> dict[str, Any]:
        preflight = self.preflight()
        if not preflight["ok"]:
            raise MemoryRebuildAppError(
                "Preflight projektu jest zablokowany: " + ", ".join(preflight["errors"])
            )
        plan = self._orchestrator().plan(self._rebuild_paths())
        payload = {
            "schema_version": "jazn_memory_rebuild_app_plan/v1",
            "generated_at_utc": utc_iso(),
            "project_id": self.project.project_id,
            "project_revision": self.project.revision,
            "preflight": preflight,
            "engine_plan": plan.to_dict(),
            "catalog_only_sources": [
                item.to_dict() for item in self.project.enabled_sources(pipeline="catalog_only")
            ],
            "html_control_sources": [
                item.to_dict() for item in self.project.enabled_sources(pipeline="html_control")
            ],
            "baseline_count": len(self.project.enabled_baselines()),
            "automatic_experience_approval": False,
            "automatic_l2": False,
            "automatic_l3": False,
        }
        self.project.last_plan = payload
        self.project.touch()
        self.save()
        return payload

    def run(self, *, confirmation: str, prepared_plan: MemoryRestorePlan | None = None) -> dict[str, Any]:
        expected = confirmation_token(self.settings())
        if confirmation != expected:
            raise MemoryRebuildAppError(f"Nieprawidłowy token potwierdzenia. Oczekiwano: {expected}")
        preflight = self.preflight()
        if not preflight["ok"]:
            raise MemoryRebuildAppError(
                "Preflight projektu jest zablokowany: " + ", ".join(preflight["errors"])
            )
        orchestrator = self._orchestrator()
        if prepared_plan is None:
            prepared_plan = orchestrator.plan(self._rebuild_paths())
        result = orchestrator.run(
            self._rebuild_paths(),
            confirmation=confirmation,
            prepared_plan=prepared_plan,
        )
        payload = {
            "schema_version": "jazn_memory_rebuild_app_run/v1",
            "generated_at_utc": utc_iso(),
            "project_id": self.project.project_id,
            "project_revision": self.project.revision,
            "engine_result": result,
            "automatic_experience_approval": False,
            "automatic_l2": False,
            "automatic_l3": False,
        }
        self.project.last_run = payload
        self.project.touch()
        self.save()
        return payload

    def compare_target_to_baselines(self, *, full_integrity: bool = False) -> dict[str, Any]:
        candidate = inspect_database_set(
            self.project.target_root,
            full_integrity=full_integrity,
            calculate_sha256=True,
        )
        comparisons: list[dict[str, Any]] = []
        for baseline in self.project.enabled_baselines():
            if not baseline.summary:
                refresh_baseline(baseline, full_integrity=full_integrity, calculate_sha256=True)
            comparisons.append(
                {
                    "baseline_id": baseline.baseline_id,
                    "label": baseline.label,
                    "path": baseline.path,
                    "comparison": compare_database_summaries(baseline.summary, candidate),
                }
            )
        return {
            "ok": bool(candidate.get("ok")) and all(
                item["comparison"].get("ok") for item in comparisons
            ),
            "generated_at_utc": utc_iso(),
            "candidate": candidate,
            "comparisons": comparisons,
        }

    def export_project_manifest(self, path: str | Path) -> Path:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.project.to_dict()
        payload["exported_at_utc"] = utc_iso()
        payload["preflight"] = self.preflight()
        self._atomic_json(target, payload)
        return target

    def export_test04_manifest(
        self,
        path: str | Path,
        *,
        baseline_test03_root: str | Path | None = None,
        legacy_memory_root: str | Path | None = None,
        attestation: dict[str, bool] | None = None,
    ) -> Path:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        selected: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        rebuild_sources = self.project.enabled_sources(pipeline="memory_rebuild")
        html_sources = self.project.enabled_sources(pipeline="html_control")
        ordered = rebuild_sources + html_sources
        selected_ids = {item.source_id for item in ordered}
        for source in self.project.enabled_sources():
            if source.source_id in selected_ids:
                continue
            excluded.append(
                {
                    "source_id": source.source_id,
                    "path": source.path,
                    "role": source.role,
                    "reason": f"pipeline_not_supported_by_test04_v1:{source.pipeline}",
                }
            )
        for source in ordered:
            if source.role in {"chatgpt_export", "journal", "approved_l0"}:
                role = source.role
                pipeline = "memory_rebuild"
            elif source.role == "chatgpt_html_export":
                role = "chatgpt_export"
                pipeline = "html_only_review"
            else:
                excluded.append(
                    {
                        "source_id": source.source_id,
                        "path": source.path,
                        "role": source.role,
                        "reason": "role_not_supported_by_test04_v1",
                    }
                )
                continue
            match = _DATE_RE.search(Path(source.path).name) or _DATE_RE.search(str(Path(source.path).parent))
            exported_at = "-".join(match.groups()) if match else None
            selected.append(
                {
                    "ordinal": len(selected) + 1,
                    "role": role,
                    "path": source.path,
                    "exported_at": exported_at,
                    "latest_export": False,
                    "pipeline": pipeline,
                    "approved": bool(source.approved),
                }
            )
        chat_indices = [index for index, item in enumerate(selected) if item["role"] == "chatgpt_export" and item["pipeline"] == "memory_rebuild"]
        if chat_indices:
            selected[chat_indices[-1]]["latest_export"] = True
        payload = {
            "schema_version": "jazn_memory_sqlite_test04_sources/v1",
            "operator_attestation": {
                "all_known_chatgpt_exports_included": False,
                "latest_export_created_immediately_before_test": False,
                "source_order_reviewed": False,
                **(attestation or {}),
            },
            "baseline_test03_root": str(Path(baseline_test03_root).expanduser().resolve()) if baseline_test03_root else "",
            "legacy_memory_root": str(Path(legacy_memory_root).expanduser().resolve()) if legacy_memory_root else "",
            "baseline_decline_justifications": {},
            "sources": selected,
            "app_metadata": {
                "project_id": self.project.project_id,
                "project_revision": self.project.revision,
                "generated_at_utc": utc_iso(),
                "excluded_sources": excluded,
                "source_family": {item.source_id: item.source_family for item in self.project.sources},
                "truth_domain": {item.source_id: item.truth_domain for item in self.project.sources},
            },
        }
        self._atomic_json(target, payload)
        return target

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)


__all__ = ["MemoryRebuildAppController", "MemoryRebuildAppError"]
