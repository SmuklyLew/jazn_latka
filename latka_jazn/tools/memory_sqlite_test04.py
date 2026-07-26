from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Sequence
import argparse
import gc
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import zipfile

from latka_jazn.tools.memory_restore import (
    DEVELOPER_CONFIRMATION,
    MemoryRestoreOrchestrator,
    MemoryRestoreSettings,
    compare_database_sets,
    resolve_database_paths,
)
from latka_jazn.tools.memory_rebuild_coordinator import (
    MemoryRebuildCoordinator,
    detect_source,
)
from latka_jazn.tools.memory_validation import (
    MemoryValidationTarget,
    validate_sqlite_target,
)
from latka_jazn.version import schema_version


EXPECTED_BRANCH = "feature/memory-sqlite-test-04"
SOURCE_MANIFEST_SCHEMA = "jazn_memory_sqlite_test04_sources/v1"
RECALL_SCHEMA = "jazn_private_recall_cases/v1"
MULTI_TURN_SCHEMA = "jazn_memory_sqlite_test04_multi_turn_review/v1"
PROTOCOL_SCHEMA = "jazn_memory_sqlite_test04/v1"
RUN_STATE_SCHEMA = "jazn_memory_sqlite_test04_run_state/v1"
TEST03_KNOWN_COUNTS = {
    "archive_chats.conversations": 474,
    "archive_chats.nodes": 65_285,
    "archive_chats.fts_docs": 49_650,
    "journal.journal_entries": 519,
    "memory_jazn.short_term_memory_index": 0,
    "memory_jazn.long_term_memory_index": 0,
}
REQUIRED_DATABASES = (
    "archive_chats",
    "journal",
    "experience",
    "memory_jazn",
    "import_catalog",
)
REQUIRED_REPORTS = (
    "settings.private.json",
    "source-inventory.private.json",
    "source-inventory.sanitized.json",
    "plan.json",
    "plan.txt",
    "events.jsonl",
    "preflight.json",
    "first-rebuild-summary.json",
    "same-target-idempotence.json",
    "fresh-rebuild-comparison.json",
    "test03-baseline-comparison.json",
    "sqlite-full-validation.json",
    "recall.sanitized.json",
    "restart-continuity.json",
    "multi-turn-review.template.json",
    "l3-status.json",
    "summary.private.json",
    "summary.sanitized.json",
)
_SOURCE_DATE_RE = re.compile(
    r"(?<!\d)(20\d{2})[._-](0[1-9]|1[0-2])[._-](0[1-9]|[12]\d|3[01])(?!\d)"
)
_FTS_SHADOW_SUFFIXES = ("_data", "_idx", "_docsize", "_config")
_VOLATILE_COLUMNS = {
    "alias_id",
    "completed_at_utc",
    "conflict_id",
    "created_at_utc",
    "details_json",
    "error_json",
    "first_seen_at_utc",
    "first_seen_import_id",
    "import_id",
    "imported_at_utc",
    "last_seen_at_utc",
    "last_seen_import_id",
    "name",
    "observed_at_utc",
    "occurrence_id",
    "operation_id",
    "path",
    "report_json",
    "revision_id",
    "seen_at_utc",
    "source_name",
    "source_path",
    "started_at_utc",
    "updated_at_utc",
}


class Test04Error(RuntimeError):
    """Fail-closed protocol error."""

    __test__ = False


@dataclass(slots=True, frozen=True)
class SourceSpec:
    ordinal: int
    role: str
    path: Path
    exported_at: str | None
    latest_export: bool
    pipeline: str
    approved: bool


@dataclass(slots=True)
class SourceManifest:
    path: Path
    sources: list[SourceSpec]
    baseline_test03_root: Path | None
    legacy_memory_root: Path | None
    attestations: dict[str, bool]
    decline_justifications: dict[str, str]
    raw_sha256: str


@dataclass(slots=True)
class ProtocolRequest:
    root: Path
    source_manifest: Path
    target_root: Path
    baseline_test03_root: Path | None = None
    legacy_memory_root: Path | None = None
    recall_cases: Path | None = None
    multi_turn_review: Path | None = None
    plan_only: bool = False
    run_rebuild: bool = False
    run_idempotence: bool = False
    run_fresh_comparison: bool = False
    run_recall: bool = False
    restart_daemon: bool = False
    restart_timeout_seconds: int = 90
    resume: bool = False
    allow_dirty: bool = False

    def normalized(self) -> "ProtocolRequest":
        return ProtocolRequest(
            root=self.root.expanduser().resolve(),
            source_manifest=self.source_manifest.expanduser().resolve(),
            target_root=self.target_root.expanduser().resolve(),
            baseline_test03_root=(
                self.baseline_test03_root.expanduser().resolve()
                if self.baseline_test03_root
                else None
            ),
            legacy_memory_root=(
                self.legacy_memory_root.expanduser().resolve()
                if self.legacy_memory_root
                else None
            ),
            recall_cases=(
                self.recall_cases.expanduser().resolve()
                if self.recall_cases
                else None
            ),
            multi_turn_review=(
                self.multi_turn_review.expanduser().resolve()
                if self.multi_turn_review
                else None
            ),
            plan_only=bool(self.plan_only),
            run_rebuild=bool(self.run_rebuild),
            run_idempotence=bool(self.run_idempotence),
            run_fresh_comparison=bool(self.run_fresh_comparison),
            run_recall=bool(self.run_recall),
            restart_daemon=bool(self.restart_daemon),
            restart_timeout_seconds=max(5, int(self.restart_timeout_seconds)),
            resume=bool(self.resume),
            allow_dirty=bool(self.allow_dirty),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_text(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _git(root: Path, *arguments: str, allow_failure: bool = False) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode and not allow_failure:
        raise Test04Error(
            f"git {' '.join(arguments)} failed with exit code "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    return completed.stdout


def repository_preflight(
    root: Path,
    *,
    expected_branch: str = EXPECTED_BRANCH,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    branch = _git(root, "branch", "--show-current").strip()
    if branch != expected_branch:
        raise Test04Error(
            f"wrong branch: expected {expected_branch!r}, got {branch!r}"
        )
    head = _git(root, "rev-parse", "HEAD").strip()
    status = [
        line
        for line in _git(root, "status", "--porcelain=v1").splitlines()
        if line.strip()
    ]
    tracked_status = [
        line
        for line in _git(
            root,
            "status",
            "--porcelain=v1",
            "--untracked-files=no",
        ).splitlines()
        if line.strip()
    ]
    if tracked_status and not allow_dirty:
        raise Test04Error(
            "tracked worktree is dirty; use a clean worktree or explicit --allow-dirty"
        )
    return {
        "branch": branch,
        "head": head,
        "status_short": status,
        "tracked_status_short": tracked_status,
        "allow_dirty": bool(allow_dirty),
        "restore_point": {
            "kind": "immutable_git_commit",
            "commit": head,
            "worktree_clean": not tracked_status,
        },
    }


def _captured_json(command: Sequence[str], cwd: Path, timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise Test04Error(
            f"command returned invalid JSON (exit={completed.returncode}): "
            f"{' '.join(command)}; {completed.stderr[-1200:]}"
        ) from exc
    payload["_exit_code"] = completed.returncode
    if completed.returncode != 0:
        raise Test04Error(
            f"command failed with exit code {completed.returncode}: "
            f"{' '.join(command)}"
        )
    return payload


def runtime_preflight(root: Path) -> dict[str, Any]:
    run_py = root / "run.py"
    if not run_py.is_file():
        raise Test04Error(f"run.py is missing: {run_py}")
    status = _captured_json(
        [
            sys.executable,
            "-X",
            "utf8",
            str(run_py),
            "status",
            "--snapshot",
            "--json",
        ],
        root,
        180.0,
    )
    doctor = _captured_json(
        [sys.executable, "-X", "utf8", str(run_py), "doctor", "--json"],
        root,
        240.0,
    )
    return {
        "status": status,
        "doctor": doctor,
        "doctor_ok": bool(doctor.get("ok")),
        "live_runtime_ready": bool(doctor.get("live_runtime_ready")),
        "activation_ready": bool(doctor.get("activation_ready")),
        "truth_boundary": (
            "Preflight records installation, runtime and release readiness separately. "
            "It does not activate memory or treat a marker as a live daemon."
        ),
    }


def validate_request(request: ProtocolRequest) -> ProtocolRequest:
    req = request.normalized()
    execution_flags = (
        req.run_rebuild,
        req.run_idempotence,
        req.run_fresh_comparison,
        req.run_recall,
        req.restart_daemon,
    )
    if req.restart_daemon and not req.run_rebuild:
        raise Test04Error("--restart-daemon requires --run-rebuild")
    if req.plan_only and any(execution_flags):
        raise Test04Error("plan-only cannot be combined with execution phase flags")
    if not req.plan_only and not req.run_rebuild:
        raise Test04Error("choose exactly one entry mode: --plan-only or --run-rebuild")
    if (req.run_idempotence or req.run_fresh_comparison or req.run_recall) and not req.run_rebuild:
        raise Test04Error("execution subphases require --run-rebuild")
    if req.run_recall and req.recall_cases is None:
        raise Test04Error("--run-recall requires --recall-cases")
    if req.recall_cases and not req.recall_cases.is_file():
        raise Test04Error("recall cases file does not exist")
    if req.multi_turn_review and not req.multi_turn_review.is_file():
        raise Test04Error("multi-turn review file does not exist")
    if not req.root.is_dir():
        raise Test04Error("repository root does not exist")
    if not req.source_manifest.is_file():
        raise Test04Error("source manifest does not exist")
    if _is_relative_to(req.target_root, req.root):
        raise Test04Error("developer target must be outside the repository")
    if req.target_root == req.source_manifest.parent:
        raise Test04Error("target root cannot equal the private source directory")
    return req


def _resolve_private_path(raw: Any, base: Path) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def load_source_manifest(path: Path) -> SourceManifest:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Test04Error(f"invalid source manifest JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise Test04Error("source manifest must be a JSON object")
    if payload.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
        raise Test04Error(
            f"unsupported source manifest schema: {payload.get('schema_version')!r}"
        )
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise Test04Error("source manifest must contain a non-empty sources array")
    sources: list[SourceSpec] = []
    for expected, item in enumerate(raw_sources, 1):
        if not isinstance(item, dict):
            raise Test04Error(f"source #{expected} must be an object")
        ordinal = int(item.get("ordinal") or 0)
        if ordinal != expected:
            raise Test04Error(
                "source ordinals must be explicit, contiguous and match array order"
            )
        role = str(item.get("role") or "").strip()
        if role not in {"chatgpt_export", "journal", "approved_l0"}:
            raise Test04Error(f"source #{ordinal} has unsupported role {role!r}")
        source_path = _resolve_private_path(item.get("path"), path.parent)
        if source_path is None:
            raise Test04Error(f"source #{ordinal} has no path")
        pipeline = str(item.get("pipeline") or "memory_rebuild").strip()
        if pipeline not in {"memory_rebuild", "html_only_review"}:
            raise Test04Error(f"source #{ordinal} has unsupported pipeline")
        approved = bool(item.get("approved", role != "approved_l0"))
        if role == "approved_l0" and not approved:
            raise Test04Error(
                f"approved_l0 source #{ordinal} requires approved=true"
            )
        sources.append(
            SourceSpec(
                ordinal=ordinal,
                role=role,
                path=source_path,
                exported_at=(
                    str(item.get("exported_at")).strip()
                    if item.get("exported_at")
                    else None
                ),
                latest_export=bool(item.get("latest_export")),
                pipeline=pipeline,
                approved=approved,
            )
        )
    latest = [
        item
        for item in sources
        if item.role == "chatgpt_export" and item.latest_export
    ]
    if len(latest) != 1:
        raise Test04Error(
            "exactly one ChatGPT export must have latest_export=true"
        )
    seen_journal = False
    for item in sources:
        if item.role == "journal":
            seen_journal = True
        elif seen_journal and item.pipeline == "memory_rebuild":
            raise Test04Error(
                "journal sources must follow all ChatGPT/approved L0 rebuild sources"
            )
    attestation_payload = payload.get("operator_attestation") or {}
    attestations = {
        "all_known_chatgpt_exports_included": bool(
            attestation_payload.get("all_known_chatgpt_exports_included")
        ),
        "latest_export_created_immediately_before_test": bool(
            attestation_payload.get("latest_export_created_immediately_before_test")
        ),
        "source_order_reviewed": bool(
            attestation_payload.get("source_order_reviewed")
        ),
    }
    justifications = payload.get("baseline_decline_justifications") or {}
    if not isinstance(justifications, dict):
        raise Test04Error("baseline_decline_justifications must be an object")
    return SourceManifest(
        path=path.resolve(),
        sources=sources,
        baseline_test03_root=_resolve_private_path(
            payload.get("baseline_test03_root"),
            path.parent,
        ),
        legacy_memory_root=_resolve_private_path(
            payload.get("legacy_memory_root"),
            path.parent,
        ),
        attestations=attestations,
        decline_justifications={
            str(key): str(value).strip()
            for key, value in justifications.items()
            if str(value).strip()
        },
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _unsafe_member_reason(name: str) -> str | None:
    value = str(name or "").replace("\\", "/")
    parts = PurePosixPath(value).parts
    if (
        not value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
        or re.match(r"^[A-Za-z]:", value)
    ):
        return "unsafe_archive_entry"
    return None


def inspect_zip_safety(path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "is_zip": True,
        "crc_checked": False,
        "crc_ok": False,
        "encrypted": False,
        "path_traversal_ok": False,
        "symlink_check_ok": False,
        "duplicate_member_check_ok": False,
        "case_collision_check_ok": False,
        "member_count": 0,
        "errors": [],
    }
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            names = [item.filename for item in infos]
            report["member_count"] = len(names)
            unsafe = [
                name for name in names if _unsafe_member_reason(name) is not None
            ]
            duplicates = sorted(
                {name for name in names if names.count(name) > 1}
            )
            by_case: dict[str, set[str]] = {}
            for name in names:
                by_case.setdefault(name.casefold(), set()).add(name)
            collisions = [
                sorted(values)
                for values in by_case.values()
                if len(values) > 1
            ]
            symlinks = [
                item.filename
                for item in infos
                if stat.S_IFMT((item.external_attr >> 16) & 0xFFFF)
                == stat.S_IFLNK
            ]
            encrypted = [
                item.filename for item in infos if bool(item.flag_bits & 0x1)
            ]
            report["path_traversal_ok"] = not unsafe
            report["symlink_check_ok"] = not symlinks
            report["duplicate_member_check_ok"] = not duplicates
            report["case_collision_check_ok"] = not collisions
            report["encrypted"] = bool(encrypted)
            if unsafe:
                report["errors"].append("path_traversal_or_absolute_member")
            if symlinks:
                report["errors"].append("symlink_member_forbidden")
            if duplicates:
                report["errors"].append("duplicate_member_paths")
            if collisions:
                report["errors"].append("case_colliding_member_paths")
            if encrypted:
                report["errors"].append("encrypted_zip_not_supported")
            bad_member = archive.testzip()
            report["crc_checked"] = True
            report["crc_ok"] = bad_member is None
            if bad_member:
                report["errors"].append("zip_crc_failure")
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        report["errors"].append(
            f"zip_open_or_crc_failed:{type(exc).__name__}"
        )
    report["ok"] = not report["errors"]
    return report


def _not_zip_safety() -> dict[str, Any]:
    return {
        "is_zip": False,
        "crc_checked": False,
        "crc_ok": None,
        "encrypted": False,
        "path_traversal_ok": None,
        "symlink_check_ok": None,
        "duplicate_member_check_ok": None,
        "case_collision_check_ok": None,
        "member_count": None,
        "errors": [],
        "ok": True,
    }


def inventory_sources(
    manifest: SourceManifest,
) -> tuple[list[dict[str, Any]], list[Path], str]:
    reports: list[dict[str, Any]] = []
    execution_paths: list[Path] = []
    seen_hashes: dict[str, int] = {}
    blocking_reasons: list[str] = []
    review_reasons: list[str] = []
    for spec in manifest.sources:
        row: dict[str, Any] = {
            "ordinal": spec.ordinal,
            "role": spec.role,
            "path": str(spec.path),
            "name": spec.path.name,
            "exported_at": spec.exported_at,
            "latest_export": spec.latest_export,
            "pipeline": spec.pipeline,
            "approved": spec.approved,
            "exists": spec.path.is_file(),
            "source_is_symlink": spec.path.is_symlink(),
            "size_bytes": 0,
            "sha256": None,
            "recognized_type": None,
            "canonical_conversation_members": [],
            "shared_conversation_members": [],
            "chat_html_available": False,
            "duplicate_of_ordinal": None,
            "include_in_execution": False,
            "errors": [],
        }
        if not row["exists"]:
            row["errors"].append("source_file_missing")
        if row["source_is_symlink"]:
            row["errors"].append("source_symlink_forbidden")
        if row["exists"] and not row["source_is_symlink"]:
            row["size_bytes"] = spec.path.stat().st_size
            row["sha256"] = _sha256_file(spec.path)
        zip_safety = (
            inspect_zip_safety(spec.path)
            if row["exists"] and spec.path.suffix.casefold() == ".zip"
            else _not_zip_safety()
        )
        row["zip_safety"] = zip_safety
        row["errors"].extend(zip_safety["errors"])
        if not row["errors"]:
            try:
                detected = detect_source(spec.path)
                row["recognized_type"] = detected.get("kind")
                row["recognized_source_kind"] = detected.get("source_kind")
                row["canonical_conversation_members"] = list(
                    detected.get("canonical_conversation_members") or []
                )
                row["shared_conversation_members"] = list(
                    detected.get("shared_conversation_members") or []
                )
                row["chat_html_available"] = bool(
                    detected.get("chat_html_available")
                )
                if spec.role == "chatgpt_export":
                    if detected.get("kind") != "chat_export":
                        row["errors"].append("manifest_role_detection_mismatch")
                    elif (
                        spec.pipeline == "memory_rebuild"
                        and not detected.get("canonical_conversations_available")
                    ):
                        row["errors"].append(
                            "canonical_conversation_json_missing"
                        )
                elif spec.role == "journal" and detected.get("kind") != "journal":
                    row["errors"].append("manifest_role_detection_mismatch")
            except Exception as exc:
                row["errors"].append(
                    f"source_detection_failed:{type(exc).__name__}:{exc}"
                )
        source_hash = row.get("sha256")
        if source_hash:
            previous = seen_hashes.get(str(source_hash))
            if previous is None:
                seen_hashes[str(source_hash)] = spec.ordinal
            else:
                row["duplicate_of_ordinal"] = previous
        row["include_in_execution"] = bool(
            not row["errors"]
            and row["duplicate_of_ordinal"] is None
            and spec.pipeline == "memory_rebuild"
        )
        if row["include_in_execution"]:
            execution_paths.append(spec.path)
        if row["errors"]:
            blocking_reasons.extend(
                f"source_{spec.ordinal}:{error}" for error in row["errors"]
            )
        if spec.pipeline == "html_only_review":
            review_reasons.append(
                f"source_{spec.ordinal}:html_only_pipeline_requires_manual_review"
            )
        reports.append(row)
    for key, value in manifest.attestations.items():
        if not value:
            review_reasons.append(f"attestation_missing:{key}")
    status = (
        "failed"
        if blocking_reasons
        else "not_reviewed"
        if review_reasons
        else "passed"
    )
    return reports, execution_paths, status


def sanitized_inventory(
    reports: Sequence[dict[str, Any]],
    source_completeness: str,
) -> dict[str, Any]:
    return {
        "schema_version": SOURCE_MANIFEST_SCHEMA,
        "source_completeness": source_completeness,
        "source_count": len(reports),
        "unique_sha256_count": len(
            {row.get("sha256") for row in reports if row.get("sha256")}
        ),
        "sources": [
            {
                "ordinal": row["ordinal"],
                "role": row["role"],
                "latest_export": row["latest_export"],
                "pipeline": row["pipeline"],
                "exists": row["exists"],
                "size_bytes": row["size_bytes"],
                "sha256": row["sha256"],
                "recognized_type": row["recognized_type"],
                "canonical_member_count": len(
                    row["canonical_conversation_members"]
                ),
                "shared_metadata_member_count": len(
                    row["shared_conversation_members"]
                ),
                "chat_html_available": row["chat_html_available"],
                "zip_safety": {
                    key: row["zip_safety"].get(key)
                    for key in (
                        "crc_checked",
                        "crc_ok",
                        "encrypted",
                        "path_traversal_ok",
                        "symlink_check_ok",
                        "duplicate_member_check_ok",
                        "case_collision_check_ok",
                        "member_count",
                        "ok",
                    )
                },
                "duplicate_of_ordinal": row["duplicate_of_ordinal"],
                "include_in_execution": row["include_in_execution"],
                "error_codes": [
                    str(item).split(":", 1)[0] for item in row["errors"]
                ],
                "path_persisted": False,
                "name_persisted": False,
            }
            for row in reports
        ],
    }


def assert_sources_unchanged(reports: Sequence[dict[str, Any]]) -> None:
    for row in reports:
        path = Path(str(row["path"]))
        if not path.is_file():
            raise Test04Error(
                f"source changed after plan: source #{row['ordinal']} is missing"
            )
        if path.stat().st_size != int(row["size_bytes"]):
            raise Test04Error(
                f"source changed after plan: size mismatch at ordinal {row['ordinal']}"
            )
        if _sha256_file(path) != row["sha256"]:
            raise Test04Error(
                f"source changed after plan: sha256 mismatch at ordinal {row['ordinal']}"
            )


def restore_settings(source_manifest: Path, target_root: Path) -> MemoryRestoreSettings:
    return MemoryRestoreSettings(
        source_directory=str(source_manifest.parent),
        target_root=str(target_root),
        mode="developer",
        recursive_scan=False,
        verify_after_each=True,
        full_validation=True,
        continue_on_error=False,
        create_backup=True,
        audit_classifiers=True,
        reclassify_journal_dry_run=True,
        apply_reclassification=False,
        analyse_topics=False,
        force_topics=False,
        candidate_limit=0,
        progress_every_conversations=5,
        baseline_roots=[],
    ).normalized()


def render_plan_text(payload: dict[str, Any]) -> str:
    lines = [
        "MEMORY SQLITE TEST 04 — PLAN BEZ ZAPISU DO CELU",
        "",
        f"schema_version: {PROTOCOL_SCHEMA}",
        f"ok: {payload.get('ok')}",
        f"selected_source_count: {payload.get('selected_source_count')}",
        f"chat_source_count: {payload.get('chat_source_count')}",
        f"journal_source_count: {payload.get('journal_source_count')}",
        f"rejected_source_count: {payload.get('rejected_source_count')}",
        f"target_root: {payload.get('settings', {}).get('target_root')}",
        "",
        "ŹRÓDŁA ROZMÓW W KOLEJNOŚCI:",
    ]
    for index, item in enumerate(payload.get("chats") or [], 1):
        plan = item.get("plan") or {}
        lines.extend(
            [
                f"{index}. {item.get('path')}",
                f"   export_relation={plan.get('export_relation')}",
                "   conversation_counters="
                + json.dumps(
                    plan.get("conversation_counters") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "   canonical_members="
                + json.dumps(
                    item.get("canonical_conversation_members") or [],
                    ensure_ascii=False,
                ),
            ]
        )
    lines.append("")
    lines.append("DZIENNIKI W KOLEJNOŚCI:")
    for index, item in enumerate(payload.get("journals") or [], 1):
        lines.append(
            f"{index}. {item.get('path')} | "
            f"valid_entries={(item.get('inspection') or {}).get('valid_entries')}"
        )
    lines.append("")
    lines.append("ODRZUCONE:")
    for item in payload.get("rejected") or []:
        lines.append(
            f"- {item.get('path')} | "
            f"{item.get('reason') or item.get('error')}"
        )
    lines.extend(
        [
            "",
            "GRANICA PRAWDY:",
            "Plan jest narastającą symulacją na tymczasowej SQLite.",
            "Nie tworzy katalogu docelowego i nie aktywuje pamięci systemowej.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_plan(
    *,
    root: Path,
    manifest_path: Path,
    target_root: Path,
    sources: Sequence[Path],
    callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[Any, dict[str, Any], str]:
    orchestrator = MemoryRestoreOrchestrator(
        restore_settings(manifest_path, target_root),
        tool_root=root,
        callback=callback,
    )
    plan = orchestrator.plan(sources)
    payload = plan.to_dict()
    return plan, payload, render_plan_text(payload)


def _readonly_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _logical_table_fingerprint(
    con: sqlite3.Connection,
    table: str,
) -> dict[str, Any]:
    columns = [
        str(row[1])
        for row in con.execute(f"PRAGMA table_info('{table}')")
        if str(row[1]) not in _VOLATILE_COLUMNS
    ]
    if table == "operations":
        columns = [
            name
            for name in ("operation_type", "target_database", "status")
            if name in {
                str(row[1])
                for row in con.execute("PRAGMA table_info('operations')")
            }
        ]
    if not columns:
        return {"columns": [], "row_count": 0, "sha256": _sha256_text("")}
    quoted = ",".join(f'"{name}"' for name in columns)
    order = ",".join(f'"{name}"' for name in columns)
    digest = hashlib.sha256()
    count = 0
    for row in con.execute(
        f'SELECT {quoted} FROM "{table}" ORDER BY {order}'
    ):
        digest.update(_json_bytes(list(row)))
        digest.update(b"\n")
        count += 1
    return {"columns": columns, "row_count": count, "sha256": digest.hexdigest()}


def logical_database_snapshot(root: Path) -> dict[str, Any]:
    databases: dict[str, Any] = {}
    for name, path in resolve_database_paths(root).items():
        if not path.is_file():
            databases[name] = {"exists": False}
            continue
        with _readonly_connection(path) as con:
            tables = [
                str(row[0])
                for row in con.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            schema_text = "\n".join(
                str(row[0] or "")
                for row in con.execute(
                    "SELECT sql FROM sqlite_master "
                    "WHERE sql IS NOT NULL ORDER BY type,name"
                )
            )
            counts = {
                table: int(
                    con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                )
                for table in tables
            }
            fingerprints = {}
            for table in tables:
                if table.endswith(_FTS_SHADOW_SUFFIXES):
                    continue
                if table == "operations":
                    continue
                fingerprints[table] = _logical_table_fingerprint(con, table)
            aggregate = hashlib.sha256()
            for table, value in sorted(fingerprints.items()):
                aggregate.update(table.encode("utf-8"))
                aggregate.update(value["sha256"].encode("ascii"))
            databases[name] = {
                "exists": True,
                "schema_sha256": hashlib.sha256(
                    schema_text.encode("utf-8")
                ).hexdigest(),
                "table_counts": counts,
                "stable_tables": fingerprints,
                "logical_fingerprint": aggregate.hexdigest(),
                "page_count": int(con.execute("PRAGMA page_count").fetchone()[0]),
                "freelist_count": int(
                    con.execute("PRAGMA freelist_count").fetchone()[0]
                ),
            }
    return {
        "schema_version": schema_version("memory_sqlite_test04_logical_snapshot"),
        "root_path_persisted": False,
        "databases": databases,
    }


def compare_logical_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    allow_operation_count_delta: bool,
) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    technical_differences: list[dict[str, Any]] = []
    for database in REQUIRED_DATABASES:
        left = before["databases"].get(database, {})
        right = after["databases"].get(database, {})
        if left.get("exists") != right.get("exists"):
            differences.append(
                {"database": database, "kind": "existence", "before": left.get("exists"), "after": right.get("exists")}
            )
            continue
        if left.get("schema_sha256") != right.get("schema_sha256"):
            differences.append(
                {"database": database, "kind": "schema_sha256"}
            )
        if left.get("logical_fingerprint") != right.get("logical_fingerprint"):
            table_differences = [
                table
                for table in sorted(
                    set(left.get("stable_tables", {}))
                    | set(right.get("stable_tables", {}))
                )
                if (
                    left.get("stable_tables", {}).get(table, {}).get("sha256")
                    != right.get("stable_tables", {}).get(table, {}).get("sha256")
                )
            ]
            differences.append(
                {
                    "database": database,
                    "kind": "logical_fingerprint",
                    "tables": table_differences,
                }
            )
        all_tables = sorted(
            set(left.get("table_counts", {}))
            | set(right.get("table_counts", {}))
        )
        for table in all_tables:
            old = int(left.get("table_counts", {}).get(table, 0))
            new = int(right.get("table_counts", {}).get(table, 0))
            if old == new:
                continue
            item = {
                "database": database,
                "table": table,
                "before": old,
                "after": new,
                "delta": new - old,
            }
            if (
                allow_operation_count_delta
                and database == "import_catalog"
                and table == "operations"
            ):
                technical_differences.append(item)
            else:
                differences.append(item)
    return {
        "ok": not differences,
        "differences": differences,
        "technical_differences": technical_differences,
        "comparison_basis": (
            "schema hashes, stable logical row fingerprints and table counts; "
            "SQLite file SHA/page layout is not an idempotence requirement"
        ),
    }


def full_validate_database_set(root: Path) -> dict[str, Any]:
    results: dict[str, Any] = {}
    sidecars: list[dict[str, Any]] = []
    reopen: list[dict[str, Any]] = []
    paths = resolve_database_paths(root)
    for name in REQUIRED_DATABASES:
        path = paths[name]
        result = validate_sqlite_target(
            MemoryValidationTarget(
                role=f"memory_rebuild_{name}",
                path=str(path),
                source="Memory SQLite Test 04",
                required=True,
            ),
            full=True,
            table_counts=True,
            hash_files=True,
        ).to_dict()
        results[name] = result
        wal = Path(str(path) + "-wal")
        shm = Path(str(path) + "-shm")
        journal = Path(str(path) + "-journal")
        sidecars.append(
            {
                "database": name,
                "wal_present": wal.exists(),
                "shm_present": shm.exists(),
                "journal_present": journal.exists(),
                "closed_cleanly": not wal.exists()
                and not shm.exists()
                and not journal.exists(),
            }
        )
        try:
            with _readonly_connection(path) as con:
                table_count = int(
                    con.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                    ).fetchone()[0]
                )
            reopen.append(
                {"database": name, "ok": True, "table_count": table_count}
            )
        except sqlite3.Error as exc:
            reopen.append(
                {
                    "database": name,
                    "ok": False,
                    "error_type": type(exc).__name__,
                }
            )
    sqlite_dir = root / "memory" / "sqlite"
    orphan_temporary = (
        [
            str(path.relative_to(root))
            for path in sqlite_dir.rglob("*")
            if path.is_file()
            and (
                path.name.endswith(".tmp")
                or path.name.endswith(".partial")
                or path.name.startswith("tmp-")
            )
        ]
        if sqlite_dir.is_dir()
        else []
    )
    backups: list[dict[str, Any]] = []
    backup_root = root / "backups"
    if backup_root.is_dir():
        for manifest_path in sorted(backup_root.rglob("backup_manifest.json")):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                backups.append(
                    {
                        "manifest_sha256": _sha256_file(manifest_path),
                        "ok": bool(payload.get("ok")),
                        "database_count": len(payload.get("databases") or {}),
                    }
                )
            except (OSError, json.JSONDecodeError):
                backups.append(
                    {
                        "manifest_sha256": None,
                        "ok": False,
                        "database_count": 0,
                    }
                )
    ok = (
        all(item.get("ok") for item in results.values())
        and all(item["closed_cleanly"] for item in sidecars)
        and all(item["ok"] for item in reopen)
        and not orphan_temporary
        and all(item["ok"] for item in backups)
    )
    return {
        "schema_version": schema_version("memory_sqlite_test04_validation"),
        "ok": ok,
        "validation_mode": "integrity_check",
        "databases": results,
        "sqlite_sidecars": sidecars,
        "reopen_checks": reopen,
        "orphan_temporary_files": orphan_temporary,
        "backup_manifests": backups,
        "truth_boundary": (
            "Structural SQLite validation does not prove source completeness, "
            "recall quality, restart continuity or readiness for activation."
        ),
    }


def _publish_staging(staging: Path, target: Path) -> dict[str, Any]:
    if target.exists():
        raise Test04Error(f"publication target already exists: {target}")
    if not staging.is_dir():
        raise Test04Error(f"staging root is missing: {staging}")
    last_error: PermissionError | None = None
    for attempt in range(20):
        try:
            staging.rename(target)
            last_error = None
            break
        except PermissionError as exc:
            last_error = exc
            gc.collect()
            time.sleep(min(0.5, 0.05 * (attempt + 1)))
    if last_error is not None:
        raise Test04Error(
            "staging publication failed because a database handle remained open"
        ) from last_error
    return {
        "ok": target.is_dir() and not staging.exists(),
        "method": "same_volume_atomic_directory_rename",
        "staging_closed_before_publish": True,
    }


def _relation_totals(plan_payload: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for item in plan_payload.get("chats") or []:
        for relation, count in (
            (item.get("plan") or {}).get("conversation_counters") or {}
        ).items():
            totals[str(relation)] = totals.get(str(relation), 0) + int(count)
    return totals


def compare_test03(
    target_root: Path,
    baseline_root: Path,
    *,
    plan_payload: dict[str, Any],
    inventory: Sequence[dict[str, Any]],
    justifications: dict[str, str],
) -> dict[str, Any]:
    comparison = compare_database_sets(target_root, [baseline_root])
    current_snapshot = logical_database_snapshot(target_root)
    counts = current_snapshot["databases"]
    actual = {
        "archive_chats.conversations": counts["archive_chats"]["table_counts"].get("conversations", 0),
        "archive_chats.nodes": counts["archive_chats"]["table_counts"].get("nodes", 0),
        "archive_chats.fts_docs": counts["archive_chats"]["table_counts"].get("fts_docs", 0),
        "journal.journal_entries": counts["journal"]["table_counts"].get("journal_entries", 0),
        "memory_jazn.short_term_memory_index": counts["memory_jazn"]["table_counts"].get("short_term_memory_index", 0),
        "memory_jazn.long_term_memory_index": counts["memory_jazn"]["table_counts"].get("long_term_memory_index", 0),
    }
    declines = []
    for metric, expected in TEST03_KNOWN_COUNTS.items():
        value = int(actual.get(metric, 0))
        if value < expected:
            declines.append(
                {
                    "metric": metric,
                    "known_test03": expected,
                    "test04": value,
                    "justified": bool(justifications.get(metric)),
                    "justification_sha256": (
                        _sha256_text(justifications[metric])
                        if justifications.get(metric)
                        else None
                    ),
                }
            )
    baseline_logical = comparison["baselines"][0]["logical_subset"]
    subset_errors = []
    baseline_changes = []
    for database, values in baseline_logical.items():
        for key, value in values.items():
            if int(value or 0) > 0:
                metric = f"{database}.{key}"
                item = {
                    "metric": metric,
                    "count": int(value),
                    "justified": bool(justifications.get(metric)),
                    "justification_sha256": (
                        _sha256_text(justifications[metric])
                        if justifications.get(metric)
                        else None
                    ),
                }
                if key.startswith("missing_"):
                    subset_errors.append(item)
                else:
                    baseline_changes.append(item)
    relation_totals = _relation_totals(plan_payload)
    skipped = [
        {
            "ordinal": row["ordinal"],
            "reason": (
                "identical_source_sha"
                if row.get("duplicate_of_ordinal")
                else "not_in_memory_rebuild_pipeline"
            ),
        }
        for row in inventory
        if not row.get("include_in_execution")
    ]
    conflicts = int(
        counts["archive_chats"]["table_counts"].get("import_conflicts", 0)
    )
    unexplained = [
        item for item in [*declines, *subset_errors] if not item["justified"]
    ]
    return {
        "schema_version": schema_version("memory_sqlite_test04_test03_comparison"),
        "ok": not unexplained and conflicts == 0,
        "known_test03_counts": TEST03_KNOWN_COUNTS,
        "test04_counts": actual,
        "records_preserved": {
            key: min(int(actual.get(key, 0)), value)
            for key, value in TEST03_KNOWN_COUNTS.items()
        },
        "records_new": {
            key: max(0, int(actual.get(key, 0)) - value)
            for key, value in TEST03_KNOWN_COUNTS.items()
        },
        "records_merged_by_deduplication": relation_totals,
        "records_skipped": skipped,
        "conflict_count": conflicts,
        "declines": declines,
        "baseline_subset_differences": subset_errors,
        "baseline_changed_records": baseline_changes,
        "unexplained_decline_count": len(unexplained),
        "raw_comparison_private": comparison,
    }


def load_recall_cases(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Test04Error(f"invalid recall cases JSON: {exc}") from exc
    if payload.get("schema_version") != RECALL_SCHEMA:
        raise Test04Error("unsupported recall cases schema")
    cases = payload.get("recall_cases")
    if not isinstance(cases, list) or not cases:
        raise Test04Error("full recall phase requires at least one real recall case")
    for index, item in enumerate(cases, 1):
        if not isinstance(item, dict) or not str(item.get("query") or "").strip():
            raise Test04Error(f"recall case #{index} has no query")
        query = str(item["query"]).strip()
        expected = [
            str(value)
            for key in ("expected_any", "expected_all")
            for value in (item.get(key) or [])
            if str(value).strip()
        ]
        if (
            query == "Wpisz prywatne pytanie kontrolne."
            or "oczekiwany termin A" in expected
            or "oczekiwany termin B" in expected
        ):
            raise Test04Error("recall cases still contain template placeholders")
    return payload


def _normalize_recall_text(value: Any) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", str(value or "").casefold())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return " ".join(without_marks.split())


def _collect_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_collect_strings(item))
        return result
    if isinstance(value, Iterable):
        result = []
        for item in value:
            result.extend(_collect_strings(item))
        return result
    return [str(value)]


def evaluate_recall_cases(target_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    coordinator = MemoryRebuildCoordinator(target_root)
    results = []
    for ordinal, case in enumerate(payload["recall_cases"], 1):
        query = str(case["query"])
        limit = max(1, int(case.get("limit") or 20))
        search = coordinator.search(query, limit)
        source_counts = {
            str(source): len(items or [])
            for source, items in (search.get("results") or {}).items()
        }
        joined = _normalize_recall_text(
            "\n".join(_collect_strings(search.get("results")))
        )
        expected_any = [
            str(item) for item in (case.get("expected_any") or []) if str(item)
        ]
        expected_all = [
            str(item) for item in (case.get("expected_all") or []) if str(item)
        ]
        forbidden_any = [
            str(item)
            for item in (case.get("forbidden_any") or [])
            if str(item)
        ]
        expected_sources = [
            str(item)
            for item in (case.get("expected_sources") or [])
            if str(item)
        ]
        any_matches = [
            item
            for item in expected_any
            if _normalize_recall_text(item) in joined
        ]
        all_matches = [
            item
            for item in expected_all
            if _normalize_recall_text(item) in joined
        ]
        forbidden_matches = [
            item
            for item in forbidden_any
            if _normalize_recall_text(item) in joined
        ]
        missing_expected_count = (
            (1 if expected_any and not any_matches else 0)
            + len(expected_all)
            - len(all_matches)
        )
        missing_sources = [
            source
            for source in expected_sources
            if int(source_counts.get(source, 0)) <= 0
        ]
        total_hits = sum(source_counts.values())
        minimum_hits = max(0, int(case.get("minimum_hits") or 1))
        ok = (
            bool(search.get("ok"))
            and missing_expected_count == 0
            and not forbidden_matches
            and not missing_sources
            and total_hits >= minimum_hits
        )
        results.append(
            {
                "ordinal": ordinal,
                "case_id_sha256": _sha256_text(str(case.get("id") or ordinal)),
                "query_sha256": _sha256_text(query),
                "ok": ok,
                "total_hits": total_hits,
                "source_hit_counts": source_counts,
                "minimum_hits": minimum_hits,
                "minimum_hits_met": total_hits >= minimum_hits,
                "expected_source_count": len(expected_sources),
                "missing_expected_source_count": len(missing_sources),
                "expected_any_count": len(expected_any),
                "expected_any_match_count": len(any_matches),
                "expected_all_count": len(expected_all),
                "expected_all_match_count": len(all_matches),
                "forbidden_count": len(forbidden_any),
                "false_match_count": len(forbidden_matches),
                "missing_match_count": missing_expected_count,
                "raw_query_persisted": False,
                "raw_expected_terms_persisted": False,
                "raw_results_persisted": False,
            }
        )
    return {
        "schema_version": RECALL_SCHEMA,
        "ok": all(item["ok"] for item in results),
        "case_count": len(results),
        "passed_count": sum(1 for item in results if item["ok"]),
        "failed_count": sum(1 for item in results if not item["ok"]),
        "missing_match_count": sum(item["missing_match_count"] for item in results),
        "false_match_count": sum(item["false_match_count"] for item in results),
        "cases": results,
        "private_content_persisted": False,
    }


def multi_turn_template() -> dict[str, Any]:
    return {
        "schema_version": MULTI_TURN_SCHEMA,
        "overall_status": "not_reviewed",
        "reviewed_by": "",
        "reviewed_at_utc": "",
        "checks": {
            "earlier_fact_recalled": None,
            "topic_maintained_across_turns": None,
            "memories_not_mixed": None,
            "source_and_provenance_visible": None,
            "book_scene_not_physical_event": None,
            "dream_or_vision_not_fact": None,
            "no_confabulation_after_miss": None,
            "missing_memory_admitted": None,
        },
        "private_scenario": {
            "turns": [],
            "review_notes": "",
        },
        "truth_boundary": (
            "A deterministic runner may collect evidence, but only a human operator "
            "may set overall_status to passed or failed for natural memory use."
        ),
    }


def evaluate_multi_turn_review(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "status": "not_reviewed",
            "check_count": 8,
            "passed_check_count": 0,
            "private_content_persisted": False,
        }
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("schema_version") != MULTI_TURN_SCHEMA:
        raise Test04Error("unsupported multi-turn review schema")
    status_value = str(payload.get("overall_status") or "not_reviewed")
    if status_value not in {"passed", "failed", "not_reviewed"}:
        raise Test04Error("invalid multi-turn overall_status")
    expected = set(multi_turn_template()["checks"])
    checks = payload.get("checks") or {}
    if set(checks) != expected:
        raise Test04Error("multi-turn review checklist is incomplete")
    passed_count = sum(value is True for value in checks.values())
    if status_value == "passed" and passed_count != len(expected):
        raise Test04Error(
            "multi-turn review cannot pass while checklist items are not true"
        )
    return {
        "status": status_value,
        "check_count": len(expected),
        "passed_check_count": passed_count,
        "reviewer_present": bool(str(payload.get("reviewed_by") or "").strip()),
        "review_timestamp_present": bool(
            str(payload.get("reviewed_at_utc") or "").strip()
        ),
        "private_content_persisted": False,
    }


def l3_status(target_root: Path | None) -> dict[str, Any]:
    counts: dict[str, int] = {}
    if target_root and target_root.is_dir():
        snapshot = logical_database_snapshot(target_root)
        counts = snapshot["databases"].get("memory_jazn", {}).get(
            "table_counts", {}
        )
    l2_count = int(counts.get("short_term_memory_index", 0))
    l3_count = int(counts.get("long_term_memory_index", 0))
    promotion_count = int(counts.get("promotion_ledger", 0))
    return {
        "schema_version": schema_version("memory_sqlite_test04_l3_status"),
        "l2_record_count": l2_count,
        "l3_record_count": l3_count,
        "promotion_ledger_count": promotion_count,
        "manifest_created": False,
        "manifest_reviewed": False,
        "manifest_approved": False,
        "promotion_executed": False,
        "awaiting_explicit_decision": False,
        "automatic_experience_approval": False,
        "automatic_l2": False,
        "automatic_l3": False,
        "approve_l3_manifest_sha_invoked": False,
        "ok": l2_count == 0 and l3_count == 0 and promotion_count == 0,
    }


def _checkpoint_snapshot(root: Path) -> dict[str, Any]:
    path = root / "workspace_runtime" / "runtime_session_state.json"
    if not path.is_file():
        return {
            "present": False,
            "file_sha256": None,
            "checkpoint_sha256": None,
            "previous_checkpoint_sha256": None,
            "generation": None,
            "turn_count": None,
        }
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        "present": True,
        "file_sha256": _sha256_file(path),
        "checkpoint_sha256": payload.get("checkpoint_sha256"),
        "previous_checkpoint_sha256": payload.get(
            "previous_checkpoint_sha256"
        ),
        "generation": payload.get("generation"),
        "turn_count": payload.get("turn_count"),
    }


def _wake_snapshot(status: dict[str, Any]) -> dict[str, Any]:
    wake = (
        status.get("status", {})
        .get("startup", {})
        .get("wake_state_status", {})
    ) or status.get("startup", {}).get("wake_state_status", {})
    active = wake.get("active_snapshot") or {}
    daemon = status.get("daemon") or {}
    marker = daemon.get("marker") or {}
    return {
        "snapshot_id": active.get("snapshot_id"),
        "snapshot_sha256": active.get("snapshot_sha256"),
        "validation_status": active.get("validation_status"),
        "daemon_pid": daemon.get("pid") or marker.get("daemon_pid"),
        "daemon_active_state": daemon.get("active_state"),
        "endpoint_reachable": daemon.get("endpoint_reachable"),
        "heartbeat_fresh": daemon.get("heartbeat_fresh"),
        "active_root": daemon.get("active_root"),
    }


def restart_continuity(root: Path, timeout_seconds: int) -> dict[str, Any]:
    run_py = root / "run.py"
    before_status = _captured_json(
        [
            sys.executable,
            "-X",
            "utf8",
            str(run_py),
            "status",
            "--root",
            str(root),
            "--json",
            "--no-progress",
        ],
        root,
        180.0,
    )
    before_wake = _wake_snapshot(before_status)
    before_checkpoint = _checkpoint_snapshot(root)
    if before_wake["daemon_active_state"] != "active_trusted":
        raise Test04Error(
            "restart continuity requires a verified active_trusted daemon before restart"
        )
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(run_py),
            "restart",
            "--root",
            str(root),
            "--no-progress",
        ],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(30, timeout_seconds),
        check=False,
    )
    after_status = None
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            candidate = _captured_json(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(run_py),
                    "status",
                    "--root",
                    str(root),
                    "--json",
                    "--no-progress",
                ],
                root,
                30.0,
            )
            wake = _wake_snapshot(candidate)
            if (
                wake["daemon_active_state"] == "active_trusted"
                and wake["endpoint_reachable"] is True
                and wake["heartbeat_fresh"] is True
            ):
                after_status = candidate
                break
        except Test04Error:
            pass
        time.sleep(2.0)
    after_wake = _wake_snapshot(after_status or {})
    after_checkpoint = _checkpoint_snapshot(root)
    checkpoint_same = (
        before_checkpoint["file_sha256"]
        and before_checkpoint["file_sha256"] == after_checkpoint["file_sha256"]
    )
    checkpoint_successor = (
        before_checkpoint["checkpoint_sha256"]
        and after_checkpoint["previous_checkpoint_sha256"]
        == before_checkpoint["checkpoint_sha256"]
    )
    ok = (
        completed.returncode == 0
        and after_status is not None
        and after_wake["active_root"] == str(root)
        and after_wake["snapshot_id"] == before_wake["snapshot_id"]
        and after_wake["snapshot_sha256"] == before_wake["snapshot_sha256"]
        and (checkpoint_same or checkpoint_successor)
    )
    return {
        "schema_version": schema_version("memory_sqlite_test04_restart"),
        "requested": True,
        "attempted": True,
        "restart_exit_code": completed.returncode,
        "status_recovered": after_status is not None,
        "active_root_matches": after_wake["active_root"] == str(root),
        "endpoint_reachable": after_wake["endpoint_reachable"],
        "heartbeat_fresh": after_wake["heartbeat_fresh"],
        "wake_state_id_equal": after_wake["snapshot_id"] == before_wake["snapshot_id"],
        "wake_state_sha256_equal": after_wake["snapshot_sha256"] == before_wake["snapshot_sha256"],
        "checkpoint_equal": bool(checkpoint_same),
        "checkpoint_documented_successor": bool(checkpoint_successor),
        "truth_gate_bypassed": False,
        "carryover_inherited_after_hash_mismatch": False,
        "before": {
            "wake": before_wake,
            "checkpoint": before_checkpoint,
        },
        "after": {
            "wake": after_wake,
            "checkpoint": after_checkpoint,
        },
        "ok": bool(ok),
    }


class EventWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: dict[str, Any]) -> None:
        payload = {
            "schema_version": PROTOCOL_SCHEMA,
            "timestamp_utc": _utc_now(),
            **event,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                + "\n"
            )


def _default_final_fields() -> dict[str, Any]:
    return {
        "structural_integrity": "not_run",
        "source_completeness": "not_reviewed",
        "same_target_idempotence": "not_run",
        "fresh_rebuild_reproducibility": "not_run",
        "test03_reconciliation": "not_run",
        "recall": "not_run",
        "multi_turn_review": "not_reviewed",
        "restart_continuity": "not_run",
        "l2_review": "not_created",
        "l3_decision": "not_created",
        "system_activation_ready": False,
    }


def acceptance_complete(final_fields: dict[str, Any]) -> bool:
    required_passes = (
        "structural_integrity",
        "source_completeness",
        "same_target_idempotence",
        "fresh_rebuild_reproducibility",
        "test03_reconciliation",
        "recall",
        "multi_turn_review",
    )
    return all(final_fields.get(field) == "passed" for field in required_passes)


def _placeholder(name: str) -> dict[str, Any]:
    return {
        "schema_version": PROTOCOL_SCHEMA,
        "report": name,
        "status": "not_run",
    }


class Test04Protocol:
    __test__ = False

    def __init__(
        self,
        request: ProtocolRequest,
        *,
        skip_runtime_preflight: bool = False,
    ) -> None:
        self.request = validate_request(request)
        self.skip_runtime_preflight = bool(skip_runtime_preflight)
        self.manifest = load_source_manifest(self.request.source_manifest)
        if (
            self.request.baseline_test03_root
            and self.manifest.baseline_test03_root
            and self.request.baseline_test03_root
            != self.manifest.baseline_test03_root
        ):
            raise Test04Error(
                "baseline Test 03 root parameter conflicts with source manifest"
            )
        if (
            self.request.legacy_memory_root
            and self.manifest.legacy_memory_root
            and self.request.legacy_memory_root
            != self.manifest.legacy_memory_root
        ):
            raise Test04Error(
                "legacy memory root parameter conflicts with source manifest"
            )
        self.baseline_root = (
            self.request.baseline_test03_root
            or self.manifest.baseline_test03_root
        )
        self.legacy_root = (
            self.request.legacy_memory_root
            or self.manifest.legacy_memory_root
        )
        self.run_dir: Path | None = None
        self.events: EventWriter | None = None
        self.state: dict[str, Any] = {
            "schema_version": RUN_STATE_SCHEMA,
            "completed_phases": [],
        }

    @property
    def workspace_root(self) -> Path:
        return (
            self.request.root
            / "workspace_runtime"
            / "memory_sqlite_test_04"
        )

    def _settings_payload(self) -> dict[str, Any]:
        return {
            "schema_version": PROTOCOL_SCHEMA,
            "created_at_utc": _utc_now(),
            "source_manifest": str(self.request.source_manifest),
            "source_manifest_sha256": self.manifest.raw_sha256,
            "target_root": str(self.request.target_root),
            "baseline_test03_root": str(self.baseline_root) if self.baseline_root else None,
            "legacy_memory_root": str(self.legacy_root) if self.legacy_root else None,
            "request": {
                **asdict(self.request),
                "root": str(self.request.root),
                "source_manifest": str(self.request.source_manifest),
                "target_root": str(self.request.target_root),
                "baseline_test03_root": str(self.request.baseline_test03_root) if self.request.baseline_test03_root else None,
                "legacy_memory_root": str(self.request.legacy_memory_root) if self.request.legacy_memory_root else None,
                "recall_cases": str(self.request.recall_cases) if self.request.recall_cases else None,
                "multi_turn_review": str(self.request.multi_turn_review) if self.request.multi_turn_review else None,
            },
        }

    def _find_resume_dir(self) -> Path:
        if not self.workspace_root.is_dir():
            raise Test04Error("no Test 04 run is available to resume")
        candidates = []
        for path in self.workspace_root.iterdir():
            settings = path / "settings.private.json"
            if not path.is_dir() or not settings.is_file():
                continue
            try:
                payload = json.loads(settings.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                payload.get("source_manifest_sha256") == self.manifest.raw_sha256
                and payload.get("target_root") == str(self.request.target_root)
            ):
                candidates.append(path)
        if not candidates:
            raise Test04Error(
                "no resumable run matches the source manifest and target root"
            )
        return sorted(candidates)[-1]

    def _prepare_run_dir(self) -> None:
        if self.request.resume:
            self.run_dir = self._find_resume_dir()
            state_path = self.run_dir / "state.private.json"
            if state_path.is_file():
                self.state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            self.run_dir = self.workspace_root / _run_id()
            self.run_dir.mkdir(parents=True, exist_ok=False)
            _atomic_json(
                self.run_dir / "settings.private.json",
                self._settings_payload(),
            )
        self.events = EventWriter(self.run_dir / "events.jsonl")
        if not (self.run_dir / "multi-turn-review.template.json").is_file():
            _atomic_json(
                self.run_dir / "multi-turn-review.template.json",
                multi_turn_template(),
            )

    def _phase_done(self, name: str) -> bool:
        return name in self.state.get("completed_phases", [])

    def _mark_phase(self, name: str) -> None:
        completed = self.state.setdefault("completed_phases", [])
        if name not in completed:
            completed.append(name)
        self.state["updated_at_utc"] = _utc_now()
        assert self.run_dir is not None
        _atomic_json(self.run_dir / "state.private.json", self.state)

    def _ensure_reports(self) -> None:
        assert self.run_dir is not None
        for name in REQUIRED_REPORTS:
            path = self.run_dir / name
            if path.exists():
                continue
            if name.endswith(".jsonl"):
                _atomic_text(path, "")
            elif name.endswith(".txt"):
                _atomic_text(path, "NOT RUN\n")
            else:
                _atomic_json(path, _placeholder(name))

    def execute(self) -> tuple[int, dict[str, Any]]:
        git = repository_preflight(
            self.request.root,
            allow_dirty=self.request.allow_dirty,
        )
        recall_payload = (
            load_recall_cases(self.request.recall_cases)
            if self.request.run_recall and self.request.recall_cases
            else None
        )
        if self.request.run_rebuild:
            if self.baseline_root is None or not self.baseline_root.is_dir():
                raise Test04Error(
                    "full rebuild requires an existing Test 03 baseline root"
                )
            if self.legacy_root is None or not self.legacy_root.is_dir():
                raise Test04Error(
                    "full rebuild requires an existing legacy memory baseline root"
                )
        runtime = (
            {
                "skipped_for_synthetic_test": True,
                "doctor_ok": True,
                "live_runtime_ready": False,
                "activation_ready": False,
            }
            if self.skip_runtime_preflight
            else runtime_preflight(self.request.root)
        )
        self._prepare_run_dir()
        assert self.run_dir is not None and self.events is not None
        self.events.emit({"event": "test04_started"})
        _atomic_json(
            self.run_dir / "preflight.json",
            {
                "schema_version": PROTOCOL_SCHEMA,
                "git": git,
                "runtime": runtime,
                "initial_branch": git["branch"],
                "initial_commit": git["head"],
                "initial_worktree_clean": not git["tracked_status_short"],
                "restore_point": git["restore_point"],
                "baselines": {
                    "test03": {
                        "root": str(self.baseline_root) if self.baseline_root else None,
                        "exists": bool(self.baseline_root and self.baseline_root.is_dir()),
                        "used_as_import_source": False,
                    },
                    "legacy_v15_0_3_222": {
                        "root": str(self.legacy_root) if self.legacy_root else None,
                        "exists": bool(self.legacy_root and self.legacy_root.is_dir()),
                        "used_as_import_source": False,
                        "role": "separate_baseline_and_recovery_source",
                    },
                },
            },
        )

        final_fields = _default_final_fields()
        private_summary: dict[str, Any] = {
            "schema_version": PROTOCOL_SCHEMA,
            "run_id": self.run_dir.name,
            "started_at_utc": _utc_now(),
            "initial_branch": git["branch"],
            "initial_commit": git["head"],
            "errors": [],
            "final": final_fields,
            "truth_boundary": (
                "This protocol validates a developer memory set. It never activates "
                "system memory and does not claim success on unavailable private data."
            ),
        }
        exit_code = 2
        inventory: list[dict[str, Any]] = []
        try:
            inventory, execution_paths, completeness = inventory_sources(
                self.manifest
            )
            _atomic_json(
                self.run_dir / "source-inventory.private.json",
                {
                    "schema_version": SOURCE_MANIFEST_SCHEMA,
                    "manifest_sha256": self.manifest.raw_sha256,
                    "attestations": self.manifest.attestations,
                    "source_completeness": completeness,
                    "sources": inventory,
                },
            )
            _atomic_json(
                self.run_dir / "source-inventory.sanitized.json",
                sanitized_inventory(inventory, completeness),
            )
            final_fields["source_completeness"] = completeness
            if completeness != "passed":
                raise Test04Error(
                    "source completeness is not attested or a source requires review"
                )
            if not execution_paths:
                raise Test04Error("no unique Memory Rebuild sources remain")

            target_existed_before_plan = self.request.target_root.exists()
            plan, plan_payload, plan_text = build_plan(
                root=self.request.root,
                manifest_path=self.request.source_manifest,
                target_root=self.request.target_root,
                sources=execution_paths,
                callback=self.events.emit,
            )
            _atomic_json(self.run_dir / "plan.json", plan_payload)
            _atomic_text(self.run_dir / "plan.txt", plan_text)
            if self.request.target_root.exists() != target_existed_before_plan:
                raise Test04Error("plan-only changed target existence")
            if plan_payload.get("rejected_source_count"):
                raise Test04Error("plan rejected one or more manifest sources")
            if not plan_payload.get("ok"):
                raise Test04Error("cumulative Memory Rebuild plan is blocked")
            assert_sources_unchanged(inventory)
            self._mark_phase("plan")

            if self.request.plan_only:
                exit_code = 0
                private_summary["status"] = "plan_passed"
                return self._finish(
                    exit_code,
                    private_summary,
                    inventory,
                )

            first_report = self._first_rebuild(
                execution_paths,
                inventory,
            )
            _atomic_json(
                self.run_dir / "first-rebuild-summary.json",
                first_report,
            )
            if not first_report.get("ok"):
                raise Test04Error("first rebuild failed")

            if self.request.run_idempotence:
                idempotence = self._idempotence(
                    execution_paths,
                    inventory,
                )
                _atomic_json(
                    self.run_dir / "same-target-idempotence.json",
                    idempotence,
                )
                final_fields["same_target_idempotence"] = (
                    "passed" if idempotence["ok"] else "failed"
                )
                if not idempotence["ok"]:
                    raise Test04Error("same-target idempotence failed")
                self._mark_phase("same_target_idempotence")

            if self.request.run_fresh_comparison:
                fresh = self._fresh_comparison(
                    execution_paths,
                    inventory,
                    first_snapshot=first_report["snapshot"],
                )
                _atomic_json(
                    self.run_dir / "fresh-rebuild-comparison.json",
                    fresh,
                )
                final_fields["fresh_rebuild_reproducibility"] = (
                    "passed" if fresh["ok"] else "failed"
                )
                if not fresh["ok"]:
                    raise Test04Error("fresh rebuild reproducibility failed")
                self._mark_phase("fresh_rebuild_comparison")

            baseline = compare_test03(
                self.request.target_root,
                self.baseline_root,
                plan_payload=plan_payload,
                inventory=inventory,
                justifications=self.manifest.decline_justifications,
            )
            _atomic_json(
                self.run_dir / "test03-baseline-comparison.json",
                baseline,
            )
            final_fields["test03_reconciliation"] = (
                "passed" if baseline["ok"] else "failed"
            )
            if not baseline["ok"]:
                raise Test04Error("Test 03 reconciliation failed")
            self._mark_phase("test03_reconciliation")

            validation = full_validate_database_set(self.request.target_root)
            _atomic_json(
                self.run_dir / "sqlite-full-validation.json",
                validation,
            )
            final_fields["structural_integrity"] = (
                "passed" if validation["ok"] else "failed"
            )
            if not validation["ok"]:
                raise Test04Error("full SQLite validation failed")
            self._mark_phase("sqlite_full_validation")

            if recall_payload is not None:
                recall = evaluate_recall_cases(
                    self.request.target_root,
                    recall_payload,
                )
                _atomic_json(
                    self.run_dir / "recall.sanitized.json",
                    recall,
                )
                final_fields["recall"] = (
                    "passed" if recall["ok"] else "failed"
                )
                if not recall["ok"]:
                    raise Test04Error("recall acceptance cases failed")
                self._mark_phase("recall")

            multi_turn = evaluate_multi_turn_review(
                self.request.multi_turn_review
            )
            final_fields["multi_turn_review"] = multi_turn["status"]
            private_summary["multi_turn_review"] = multi_turn
            if multi_turn["status"] == "passed":
                self._mark_phase("multi_turn_review")

            restart = {
                "schema_version": schema_version(
                    "memory_sqlite_test04_restart"
                ),
                "requested": False,
                "attempted": False,
                "status": "not_run",
            }
            if self.request.restart_daemon:
                restart = restart_continuity(
                    self.request.root,
                    self.request.restart_timeout_seconds,
                )
                final_fields["restart_continuity"] = (
                    "passed" if restart["ok"] else "failed"
                )
                if not restart["ok"]:
                    raise Test04Error("restart continuity failed")
                self._mark_phase("restart_continuity")
            _atomic_json(
                self.run_dir / "restart-continuity.json",
                restart,
            )

            l3 = l3_status(self.request.target_root)
            _atomic_json(self.run_dir / "l3-status.json", l3)
            final_fields["l2_review"] = (
                "not_created"
                if l3["l2_record_count"] == 0
                else "pending"
            )
            final_fields["l3_decision"] = (
                "not_created"
                if not l3["manifest_created"]
                else "pending"
            )
            if not l3["ok"]:
                raise Test04Error("automatic L2/L3 materialization was detected")
            self._mark_phase("l2_l3_status")
            final_fields["system_activation_ready"] = False
            if acceptance_complete(final_fields):
                private_summary["status"] = "completed_requested_phases"
                exit_code = 0
            else:
                if multi_turn["status"] == "not_reviewed":
                    private_summary["status"] = (
                        "awaiting_manual_multi_turn_review"
                    )
                elif multi_turn["status"] == "failed":
                    private_summary["status"] = (
                        "manual_multi_turn_review_failed"
                    )
                else:
                    private_summary["status"] = (
                        "required_acceptance_phase_not_passed"
                    )
                exit_code = 2
        except Exception as exc:
            private_summary["status"] = "failed"
            private_summary["errors"].append(
                {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            self.events.emit(
                {
                    "event": "test04_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            exit_code = 2
        return self._finish(exit_code, private_summary, inventory)

    def _first_rebuild(
        self,
        execution_paths: Sequence[Path],
        inventory: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        assert self.run_dir is not None and self.events is not None
        if self._phase_done("first_rebuild") and self.request.target_root.is_dir():
            validation = full_validate_database_set(self.request.target_root)
            if not validation["ok"]:
                raise Test04Error(
                    "completed first rebuild target failed resume validation"
                )
            stored_report_path = self.run_dir / "first-rebuild-summary.json"
            stored_snapshot = None
            if stored_report_path.is_file():
                try:
                    stored_report = json.loads(
                        stored_report_path.read_text(encoding="utf-8")
                    )
                    candidate = stored_report.get("snapshot")
                    if isinstance(candidate, dict):
                        stored_snapshot = candidate
                except (OSError, json.JSONDecodeError):
                    stored_snapshot = None
            return {
                "ok": True,
                "status": "resumed_completed_phase",
                "target_root": str(self.request.target_root),
                "validation": validation,
                "snapshot": (
                    stored_snapshot
                    or logical_database_snapshot(self.request.target_root)
                ),
                "snapshot_source": (
                    "stored_first_rebuild_report"
                    if stored_snapshot is not None
                    else "validated_current_target_before_later_phases"
                ),
            }
        staging = self.request.target_root.with_name(
            f".{self.request.target_root.name}.test04-{self.run_dir.name}-a.staging"
        )
        if self.request.target_root.exists():
            if not self.request.resume:
                raise Test04Error(
                    "first rebuild target already exists; use --resume only for this run"
                )
            validation = full_validate_database_set(self.request.target_root)
            if validation["ok"]:
                self._mark_phase("first_rebuild")
                return {
                    "ok": True,
                    "status": "resumed_existing_published_target",
                    "target_root": str(self.request.target_root),
                    "validation": validation,
                    "snapshot": logical_database_snapshot(
                        self.request.target_root
                    ),
                }
            raise Test04Error("existing resume target is not a valid five-database set")
        staging.parent.mkdir(parents=True, exist_ok=True)
        orchestrator = MemoryRestoreOrchestrator(
            restore_settings(self.request.source_manifest, staging),
            tool_root=self.request.root,
            callback=self.events.emit,
        )
        execution_plan = orchestrator.plan(execution_paths)
        _atomic_json(
            self.run_dir / "execution-plan.private.json",
            execution_plan.to_dict(),
        )
        assert_sources_unchanged(inventory)
        result = orchestrator.run(
            execution_paths,
            confirmation=DEVELOPER_CONFIRMATION,
            prepared_plan=execution_plan,
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "status": "rebuild_failed",
                "orchestrator": result,
                "staging_root": str(staging),
            }
        validation = full_validate_database_set(staging)
        if not validation["ok"]:
            return {
                "ok": False,
                "status": "staging_validation_failed",
                "orchestrator": result,
                "validation": validation,
                "staging_root": str(staging),
            }
        publication = _publish_staging(staging, self.request.target_root)
        self._mark_phase("first_rebuild")
        return {
            "ok": bool(publication["ok"]),
            "status": "published",
            "orchestrator": result,
            "staging_validation": validation,
            "publication": publication,
            "target_root": str(self.request.target_root),
            "snapshot": logical_database_snapshot(self.request.target_root),
            "automatic_l2": False,
            "automatic_l3": False,
        }

    def _idempotence(
        self,
        execution_paths: Sequence[Path],
        inventory: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        assert self.events is not None
        before = logical_database_snapshot(self.request.target_root)
        assert_sources_unchanged(inventory)
        orchestrator = MemoryRestoreOrchestrator(
            restore_settings(
                self.request.source_manifest,
                self.request.target_root,
            ),
            tool_root=self.request.root,
            callback=self.events.emit,
        )
        plan = orchestrator.plan(execution_paths)
        result = orchestrator.run(
            execution_paths,
            confirmation=DEVELOPER_CONFIRMATION,
            prepared_plan=plan,
        )
        after = logical_database_snapshot(self.request.target_root)
        comparison = compare_logical_snapshots(
            before,
            after,
            allow_operation_count_delta=True,
        )
        status = MemoryRebuildCoordinator(self.request.target_root).status()
        layer_ok = (
            not status["counts"]["experience"].get("candidates")
            and not status["counts"]["experience"].get("experiences")
            and not status["counts"]["memory_jazn"].get("short_term_memory_index")
            and not status["counts"]["memory_jazn"].get("long_term_memory_index")
        )
        chat_plan_rows = plan.to_dict().get("chats") or []
        recognized_existing = all(
            item.get("plan", {}).get("export_relation")
            == "identical_export_duplicate"
            for item in chat_plan_rows
        )
        return {
            "schema_version": schema_version(
                "memory_sqlite_test04_idempotence"
            ),
            "ok": (
                bool(result.get("ok"))
                and comparison["ok"]
                and layer_ok
                and recognized_existing
            ),
            "orchestrator": result,
            "before": before,
            "after": after,
            "comparison": comparison,
            "sources_recognized_as_existing": recognized_existing,
            "path_independence_basis": (
                "source SHA-256 deduplication plus stable logical fingerprints; "
                "source path and source name are excluded from logical equality"
            ),
            "no_l2_l3_created": layer_ok,
        }

    def _fresh_comparison(
        self,
        execution_paths: Sequence[Path],
        inventory: Sequence[dict[str, Any]],
        *,
        first_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        assert self.run_dir is not None and self.events is not None
        target_b = self.request.target_root.with_name(
            self.request.target_root.name + "_rebuild_b"
        )
        staging_b = target_b.with_name(
            f".{target_b.name}.test04-{self.run_dir.name}.staging"
        )
        if target_b.exists() and not self.request.resume:
            raise Test04Error("fresh comparison target already exists")
        if not target_b.exists():
            orchestrator = MemoryRestoreOrchestrator(
                restore_settings(self.request.source_manifest, staging_b),
                tool_root=self.request.root,
                callback=self.events.emit,
            )
            plan = orchestrator.plan(execution_paths)
            assert_sources_unchanged(inventory)
            result = orchestrator.run(
                execution_paths,
                confirmation=DEVELOPER_CONFIRMATION,
                prepared_plan=plan,
            )
            if not result.get("ok"):
                return {
                    "ok": False,
                    "status": "second_rebuild_failed",
                    "orchestrator": result,
                }
            validation = full_validate_database_set(staging_b)
            if not validation["ok"]:
                return {
                    "ok": False,
                    "status": "second_staging_validation_failed",
                    "validation": validation,
                }
            publication = _publish_staging(staging_b, target_b)
        else:
            result = {"ok": True, "status": "resumed_existing_target_b"}
            validation = full_validate_database_set(target_b)
            publication = {"ok": validation["ok"], "method": "already_published"}
        first = first_snapshot
        second = logical_database_snapshot(target_b)
        comparison = compare_logical_snapshots(
            first,
            second,
            allow_operation_count_delta=False,
        )
        return {
            "schema_version": schema_version(
                "memory_sqlite_test04_fresh_comparison"
            ),
            "ok": bool(
                result.get("ok")
                and validation.get("ok")
                and publication.get("ok")
                and comparison.get("ok")
            ),
            "target_b_path_persisted": True,
            "target_b": str(target_b),
            "orchestrator": result,
            "validation": validation,
            "publication": publication,
            "first": first,
            "second": second,
            "comparison": comparison,
        }

    def _finish(
        self,
        exit_code: int,
        private_summary: dict[str, Any],
        inventory: Sequence[dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        assert self.run_dir is not None and self.events is not None
        final_fields = private_summary["final"]
        final_fields["system_activation_ready"] = False
        private_summary["finished_at_utc"] = _utc_now()
        private_summary["exit_code"] = exit_code
        private_summary["system_activation_performed"] = False
        private_summary["private_sources_processed"] = bool(
            self.request.run_rebuild
        )
        _atomic_json(
            self.run_dir / "summary.private.json",
            private_summary,
        )
        sanitized = {
            "schema_version": PROTOCOL_SCHEMA,
            "run_id_sha256": _sha256_text(self.run_dir.name),
            "generated_at_utc": _utc_now(),
            "initial_branch": private_summary.get("initial_branch"),
            "initial_commit": private_summary.get("initial_commit"),
            "source_count": len(inventory),
            "unique_source_sha256_count": len(
                {row.get("sha256") for row in inventory if row.get("sha256")}
            ),
            "final": final_fields,
            "error_count": len(private_summary.get("errors") or []),
            "error_types": [
                item.get("error_type")
                for item in private_summary.get("errors") or []
            ],
            "full_paths_persisted": False,
            "source_names_persisted": False,
            "recall_queries_persisted": False,
            "expected_terms_persisted": False,
            "conversation_content_persisted": False,
            "system_activation_performed": False,
            "truth_boundary": private_summary["truth_boundary"],
        }
        _atomic_json(
            self.run_dir / "summary.sanitized.json",
            sanitized,
        )
        self._ensure_reports()
        self.events.emit(
            {
                "event": "test04_finished",
                "exit_code": exit_code,
                "system_activation_ready": False,
            }
        )
        return exit_code, sanitized


def write_templates(root: Path) -> list[Path]:
    template_root = root / "docs" / "templates" / "memory_sqlite_test_04"
    destination = root / "workspace_runtime" / "memory_sqlite_test_04"
    if not template_root.is_dir():
        raise Test04Error(f"tracked template directory is missing: {template_root}")
    destination.mkdir(parents=True, exist_ok=True)
    written = []
    for source in template_root.glob("*.template.json"):
        target = destination / source.name
        if target.exists():
            raise Test04Error(f"private template already exists: {target}")
        shutil.copyfile(source, target)
        written.append(target)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Memory SQLite Test 04 private operator core.",
        allow_abbrev=False,
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--target-root", type=Path)
    parser.add_argument("--baseline-test03-root", type=Path)
    parser.add_argument("--legacy-memory-root", type=Path)
    parser.add_argument("--recall-cases", type=Path)
    parser.add_argument("--multi-turn-review", type=Path)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--run-rebuild", action="store_true")
    parser.add_argument("--run-idempotence", action="store_true")
    parser.add_argument("--run-fresh-rebuild-comparison", action="store_true")
    parser.add_argument("--run-recall", action="store_true")
    parser.add_argument("--restart-daemon", action="store_true")
    parser.add_argument("--restart-timeout-seconds", type=int, default=90)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--write-templates", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = args.root.expanduser().resolve()
        if args.write_templates:
            repository_preflight(root, allow_dirty=bool(args.allow_dirty))
            paths = write_templates(root)
            payload = {
                "ok": True,
                "written": [str(path) for path in paths],
                "private_workspace_only": True,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.source_manifest is None or args.target_root is None:
            raise Test04Error(
                "--source-manifest and --target-root are required"
            )
        request = ProtocolRequest(
            root=root,
            source_manifest=args.source_manifest,
            target_root=args.target_root,
            baseline_test03_root=args.baseline_test03_root,
            legacy_memory_root=args.legacy_memory_root,
            recall_cases=args.recall_cases,
            multi_turn_review=args.multi_turn_review,
            plan_only=args.plan_only,
            run_rebuild=args.run_rebuild,
            run_idempotence=args.run_idempotence,
            run_fresh_comparison=args.run_fresh_rebuild_comparison,
            run_recall=args.run_recall,
            restart_daemon=args.restart_daemon,
            restart_timeout_seconds=args.restart_timeout_seconds,
            resume=args.resume,
            allow_dirty=args.allow_dirty,
        )
        code, payload = Test04Protocol(request).execute()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return code
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": "KeyboardInterrupt",
                    "error": "Test 04 interrupted; use --resume after inspection.",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 130
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "system_activation_performed": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXPECTED_BRANCH",
    "MULTI_TURN_SCHEMA",
    "PROTOCOL_SCHEMA",
    "ProtocolRequest",
    "RECALL_SCHEMA",
    "SOURCE_MANIFEST_SCHEMA",
    "SourceManifest",
    "SourceSpec",
    "Test04Error",
    "Test04Protocol",
    "assert_sources_unchanged",
    "build_plan",
    "compare_logical_snapshots",
    "evaluate_multi_turn_review",
    "evaluate_recall_cases",
    "full_validate_database_set",
    "inspect_zip_safety",
    "inventory_sources",
    "load_recall_cases",
    "load_source_manifest",
    "logical_database_snapshot",
    "main",
    "multi_turn_template",
    "repository_preflight",
    "restore_settings",
    "sanitized_inventory",
    "validate_request",
    "write_templates",
]
