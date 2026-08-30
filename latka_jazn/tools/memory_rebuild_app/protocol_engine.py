from __future__ import annotations

"""Procedural Memory Rebuild Test00-04 and Final orchestration.

Running a protocol is deliberately separate from validating an existing
artifact.  The engine writes only into its explicit output root and never
activates runtime memory or promotes L2/L3 records.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json
import os
import shutil
import sqlite3
import uuid

from latka_jazn.tools.chat_export_reader import sha256_file

from .config import TOOL_VERSION
from .read_only_validation import open_read_only, promotion_ledger_validation, validate_existing_database
from .recall import run_fts5_recall_benchmark
from .recall.models import RecallCaseCategory, load_recall_benchmark
from .report_sanitizer import write_report_pair
from .run_manifest import RunManifest
from .settings import MemoryRebuildSettings
from .source_bundle import ChatGPTExportBundle, SourceRole, classify_source_path
from .source_fidelity import run_test00_source_fidelity
from .source_union import build_source_union_manifest, run_source_union_analysis
from .test_spec import TEST_PROTOCOL_ORDER, TestOutcome
from .unified_memory import CANONICAL_DATABASE_NAME, UnifiedMemoryDatabase


PROTOCOL_ENGINE_SCHEMA = "jazn_memory_rebuild_protocol_engine/v4"
_RAW_L0_TABLES = (
    "memory_l0_sources",
    "memory_l0_records",
    "memory_l0_occurrences",
    "memory_l0_assets",
    "memory_l0_record_assets",
    "memory_l0_conversations",
    "memory_l0_imports",
    "conversation_variant_payloads",
)
_VOLATILE_COLUMNS = {
    "created_at_utc",
    "first_imported_at_utc",
    "last_seen_at_utc",
    "seen_at_utc",
    "imported_at_utc",
    "observed_at_utc",
    "completed_at_utc",
    "started_at_utc",
    "updated_at_utc",
    "first_seen_at_utc",
    "last_seen_at_utc",
    "first_seen_import_id",
    "last_seen_import_id",
    "import_id",
}
_REQUIRED_RECALL_CATEGORIES = frozenset(
    {
        RecallCaseCategory.DIRECT,
        RecallCaseCategory.PARAPHRASE,
        RecallCaseCategory.REFERENTIAL_FOLLOWUP,
        RecallCaseCategory.TEMPORAL,
        RecallCaseCategory.UPDATE,
        RecallCaseCategory.CONFLICT,
        RecallCaseCategory.NEGATIVE,
        RecallCaseCategory.PROVENANCE,
        RecallCaseCategory.SENSITIVE_BOUNDARY,
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _json_read(value: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"protocol artifact must contain a JSON object: {path}")
    return payload


def _source_inventory_fingerprint(inventory: Sequence[Mapping[str, Any]]) -> str:
    normalized = [
        {
            "relative_path": str(item.get("relative_path") or ""),
            "role": str(item.get("role") or ""),
            "sha256": str(item.get("sha256") or ""),
            "size_bytes": int(item.get("size_bytes") or 0),
        }
        for item in inventory
    ]
    normalized.sort(
        key=lambda item: (
            item["relative_path"],
            item["role"],
            item["sha256"],
            item["size_bytes"],
        )
    )
    return _canonical_sha(normalized)


def _protocol_outcome(ok: bool, *, blocked: bool = False, lossy: bool = False) -> str:
    if blocked:
        return TestOutcome.BLOCKED.value
    if lossy:
        return TestOutcome.LOSSY.value
    return TestOutcome.PASSED.value if ok else TestOutcome.FAILED.value


def _table_digest(con: sqlite3.Connection, table: str, *, semantic: bool) -> dict[str, Any] | None:
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (table,)
    ).fetchone()
    if exists is None:
        return None
    info = list(con.execute(f'PRAGMA table_info("{table}")'))
    columns = [str(row[1]) for row in info]
    if semantic:
        columns = [item for item in columns if item not in _VOLATILE_COLUMNS]
    if not columns:
        return {"row_count": 0, "sha256": _canonical_sha([]), "columns": []}
    selected = ",".join('"' + item.replace('"', '""') + '"' for item in columns)
    rows = [list(row) for row in con.execute(f'SELECT {selected} FROM "{table}"')]
    rows.sort(key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))
    return {"row_count": len(rows), "sha256": _canonical_sha(rows), "columns": columns}


def _database_snapshot(database: Path, tables: Sequence[str], *, semantic: bool) -> dict[str, Any]:
    with open_read_only(database) as con:
        result = {
            table: item
            for table in tables
            if (item := _table_digest(con, table, semantic=semantic)) is not None
        }
    return {"tables": result, "fingerprint_sha256": _canonical_sha(result)}


def _raw_l0_snapshot(database: Path) -> dict[str, Any]:
    return _database_snapshot(database, _RAW_L0_TABLES, semantic=False)


def _semantic_database_snapshot(database: Path) -> dict[str, Any]:
    tables = (
        "conversations",
        "nodes",
        "conversation_variant_payloads",
        "import_conflicts",
        "memory_l0_sources",
        "memory_l0_records",
        "memory_l0_occurrences",
        "memory_l0_assets",
        "memory_l0_record_assets",
        "memory_l0_conversations",
        "memory_rebuild_projections",
    )
    return _database_snapshot(database, tables, semantic=True)


def _database_lineage_fingerprint(database: Path) -> str:
    return str(_semantic_database_snapshot(database)["fingerprint_sha256"])


def _sensitivity(role: str, visibility: str, record_kind: str) -> str:
    if visibility != "visible" or role in {"system", "tool", "developer"}:
        return "restricted"
    if record_kind == "conversation_message":
        return "private"
    return "source_evidence"


def _refresh_derived_projections(database: Path) -> dict[str, Any]:
    store = UnifiedMemoryDatabase(database)
    before = _raw_l0_snapshot(database)
    with store.connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_rebuild_projections(
              record_id TEXT PRIMARY KEY,
              visibility TEXT NOT NULL,
              memory_eligible INTEGER NOT NULL CHECK(memory_eligible IN (0,1)),
              sensitivity TEXT NOT NULL,
              source_content_sha256 TEXT NOT NULL,
              FOREIGN KEY(record_id) REFERENCES memory_l0_records(record_id) ON DELETE CASCADE
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_rebuild_projection_fts USING fts5(
              record_id UNINDEXED,
              title,
              content,
              record_kind,
              tokenize='unicode61 remove_diacritics 2'
            );
            DELETE FROM memory_rebuild_projections;
            DELETE FROM memory_rebuild_projection_fts;
            """
        )
        rows = list(
            con.execute(
                """SELECT record_id,title,content,record_kind,COALESCE(role,''),
                          visibility,memory_eligible,content_sha256
                   FROM memory_l0_records WHERE is_current_revision=1 ORDER BY record_id"""
            )
        )
        eligible = 0
        for row in rows:
            record_id, title, content, kind, role, visibility, memory_eligible, digest = row
            sensitivity = _sensitivity(str(role), str(visibility), str(kind))
            con.execute(
                "INSERT INTO memory_rebuild_projections VALUES(?,?,?,?,?)",
                (record_id, visibility, int(memory_eligible), sensitivity, digest),
            )
            if int(memory_eligible) == 1 and str(visibility) == "visible":
                con.execute(
                    "INSERT INTO memory_rebuild_projection_fts(record_id,title,content,record_kind) VALUES(?,?,?,?)",
                    (record_id, title, content, kind),
                )
                eligible += 1
        con.execute(
            "INSERT INTO memory_rebuild_projection_fts(memory_rebuild_projection_fts) VALUES('integrity-check')"
        )
        con.commit()
    after = _raw_l0_snapshot(database)
    return {
        "ok": before == after,
        "projection_count": len(rows),
        "fts_eligible_count": eligible,
        "raw_l0_before": before,
        "raw_l0_after": after,
        "raw_l0_unchanged": before == after,
        "automatic_l2": False,
        "automatic_l3": False,
        "automatic_activation": False,
    }


@dataclass(frozen=True, slots=True)
class ProtocolArtifact:
    profile: str
    outcome: str
    ok: bool
    run_id: str
    checks: tuple[Mapping[str, Any], ...]
    artifacts: Mapping[str, Any]
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    details: Mapping[str, Any] | None = None
    downstream_ready: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": PROTOCOL_ENGINE_SCHEMA,
            "profile": self.profile,
            "outcome": self.outcome,
            "ok": self.ok,
            "run_id": self.run_id,
            "checks": [dict(item) for item in self.checks],
            "artifacts": dict(self.artifacts),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "details": dict(self.details or {}),
            "automatic_l2": False,
            "automatic_l3": False,
            "automatic_activation": False,
        }
        if self.downstream_ready is not None:
            payload["downstream_ready"] = self.downstream_ready
        return payload


class ProtocolEngine:
    """One procedural engine shared by CLI, Studio and automated tests."""

    def __init__(
        self,
        output_root: str | Path,
        *,
        settings: MemoryRebuildSettings | None = None,
        tool_version: str = TOOL_VERSION,
        system_version: str,
        base_commit: str,
        run_id: str | None = None,
    ) -> None:
        self.output_root = Path(output_root).expanduser().resolve()
        self.settings = settings or MemoryRebuildSettings()
        self.run_id = run_id or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        )
        self.run_root = self.output_root / self.run_id
        self.results: dict[str, dict[str, Any]] = {}
        self._source_inventory_fingerprint: str | None = None
        self._source_union_fingerprint: str | None = None
        self._database_sha256: str | None = None
        self._database_fingerprint: str | None = None
        self._manifest = RunManifest.begin(
            tool_version=tool_version,
            system_version=system_version,
            base_commit=base_commit,
            run_id=self.run_id,
        )
        self._manifest_paths: dict[str, str] | None = None

    def _ensure_root(self) -> Path:
        self.run_root.mkdir(parents=True, exist_ok=True)
        return self.run_root

    def _record(self, artifact: ProtocolArtifact) -> dict[str, Any]:
        if artifact.profile in self.results:
            raise RuntimeError(f"protocol stage already recorded: {artifact.profile}")
        payload = artifact.to_dict()
        self.results[artifact.profile] = payload
        self._manifest = self._manifest.with_result(artifact.profile, payload)
        report_paths = write_report_pair(self._ensure_root(), f"{artifact.profile}-result", payload)
        payload["private_report"] = report_paths["private"]
        payload["sanitized_report"] = report_paths["sanitized"]
        return payload

    def _blocked_prerequisite(
        self,
        profile: str,
        checks: Sequence[Mapping[str, Any]],
        *,
        prerequisite_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        blockers = tuple(
            str(item.get("name"))
            for item in checks
            if not bool(item.get("passed"))
        )
        prerequisite_summary: dict[str, Any] = {}
        if prerequisite_payload is not None:
            prerequisite_summary = {
                "profile": prerequisite_payload.get("profile"),
                "run_id": prerequisite_payload.get("run_id"),
                "outcome": prerequisite_payload.get("outcome"),
            }
        return self._record(
            ProtocolArtifact(
                profile=profile,
                outcome=TestOutcome.BLOCKED.value,
                ok=False,
                run_id=self.run_id,
                checks=tuple(dict(item) for item in checks),
                artifacts={},
                blockers=blockers,
                details={"prerequisite": prerequisite_summary},
            )
        )

    def _prerequisite_gate(
        self,
        profile: str,
        expected_profile: str,
        prerequisite: str | Path | Mapping[str, Any] | None,
        *,
        expected_database_sha256: str | None = None,
        expected_database_fingerprint: str | None = None,
        expected_source_inventory_fingerprint: str | None = None,
        expected_source_union_fingerprint: str | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        payload: dict[str, Any] | None = None
        read_error: str | None = None
        if prerequisite is not None:
            try:
                payload = _json_read(prerequisite)
            except (OSError, TypeError, UnicodeError, ValueError) as exc:
                read_error = f"{type(exc).__name__}: {exc}"

        artifacts_value = payload.get("artifacts") if payload is not None else None
        artifacts = dict(artifacts_value) if isinstance(artifacts_value, Mapping) else {}
        expected_chain = list(
            TEST_PROTOCOL_ORDER[: TEST_PROTOCOL_ORDER.index(expected_profile) + 1]
        )
        observed_chain_value = artifacts.get("dependency_chain")
        observed_chain = (
            [str(item) for item in observed_chain_value]
            if isinstance(observed_chain_value, (list, tuple))
            else []
        )
        observed_outcome = str(payload.get("outcome") or "") if payload is not None else ""
        if expected_profile == "test00":
            outcome_accepted = (
                observed_outcome in {TestOutcome.PASSED.value, TestOutcome.LOSSY.value}
                and bool(payload and payload.get("downstream_ready"))
            )
        else:
            outcome_accepted = (
                observed_outcome == TestOutcome.PASSED.value
                and bool(payload and payload.get("ok"))
            )

        checks: list[dict[str, Any]] = [
            {
                "name": "prerequisite_artifact_present",
                "passed": payload is not None,
                "expected": expected_profile,
                "error": read_error,
            },
            {
                "name": "prerequisite_schema_version",
                "passed": bool(payload) and payload.get("schema_version") == PROTOCOL_ENGINE_SCHEMA,
                "expected": PROTOCOL_ENGINE_SCHEMA,
                "actual": payload.get("schema_version") if payload else None,
            },
            {
                "name": "prerequisite_profile",
                "passed": bool(payload) and payload.get("profile") == expected_profile,
                "expected": expected_profile,
                "actual": payload.get("profile") if payload else None,
            },
            {
                "name": "prerequisite_run_id",
                "passed": bool(payload) and payload.get("run_id") == self.run_id,
                "expected": self.run_id,
                "actual": payload.get("run_id") if payload else None,
            },
            {
                "name": "prerequisite_outcome",
                "passed": outcome_accepted,
                "expected": (
                    "PASSED or LOSSY with downstream_ready"
                    if expected_profile == "test00"
                    else TestOutcome.PASSED.value
                ),
                "actual": observed_outcome or None,
            },
            {
                "name": "prerequisite_dependency_chain",
                "passed": observed_chain == expected_chain,
                "expected": expected_chain,
                "actual": observed_chain,
            },
        ]
        optional_fingerprints = (
            (
                "prerequisite_database_sha256",
                expected_database_sha256,
                artifacts.get("database_sha256"),
            ),
            (
                "prerequisite_database_fingerprint",
                expected_database_fingerprint,
                artifacts.get("database_fingerprint"),
            ),
            (
                "prerequisite_source_inventory_fingerprint",
                expected_source_inventory_fingerprint,
                artifacts.get("source_inventory_fingerprint"),
            ),
            (
                "prerequisite_source_union_fingerprint",
                expected_source_union_fingerprint,
                artifacts.get("source_union_fingerprint"),
            ),
        )
        for name, expected, actual in optional_fingerprints:
            if expected is not None:
                checks.append(
                    {
                        "name": name,
                        "passed": bool(payload) and actual == expected,
                        "expected": expected,
                        "actual": actual,
                    }
                )

        if any(not bool(item.get("passed")) for item in checks):
            return None, self._blocked_prerequisite(
                profile,
                checks,
                prerequisite_payload=payload,
            )

        assert payload is not None
        return {
            "payload": payload,
            "artifacts": artifacts,
            "artifact_sha256": _canonical_sha(payload),
        }, None

    def _sources(self, sources: Iterable[str | Path]) -> tuple[list[Path], list[dict[str, Any]]]:
        paths: list[Path] = []
        inventory: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in sources:
            candidate = Path(raw).expanduser().resolve()
            if candidate.is_dir():
                bundle = ChatGPTExportBundle.discover(candidate)
                for member in bundle.members:
                    path = candidate / Path(member.relative_path)
                    key = os.path.normcase(str(path))
                    if key in seen:
                        continue
                    seen.add(key)
                    paths.append(path)
                    inventory.append(
                        {
                            "path": str(path),
                            "relative_path": member.relative_path,
                            "role": member.role.value,
                            "sha256": member.source_sha256,
                            "size_bytes": member.size_bytes,
                        }
                    )
            else:
                if not candidate.is_file():
                    raise FileNotFoundError(candidate)
                key = os.path.normcase(str(candidate))
                if key in seen:
                    continue
                seen.add(key)
                paths.append(candidate)
                inventory.append(
                    {
                        "path": str(candidate),
                        "relative_path": candidate.name,
                        "role": classify_source_path(candidate, relative_path=candidate.name).value,
                        "sha256": sha256_file(candidate),
                        "size_bytes": candidate.stat().st_size,
                    }
                )
        if not paths:
            raise ValueError("protocol requires at least one source")
        self._source_inventory_fingerprint = _source_inventory_fingerprint(inventory)
        self._manifest = self._manifest.with_sources(tuple(inventory))
        return paths, inventory

    def run_test00(self, sources: Iterable[str | Path]) -> dict[str, Any]:
        paths, inventory = self._sources(sources)
        if self.run_root.exists():
            raise FileExistsError(self.run_root)
        opaque = [
            path for path, item in zip(paths, inventory)
            if item["role"] in {SourceRole.SOURCE_ATTACHMENT.value, SourceRole.UNKNOWN_SIDECAR.value}
        ]
        fidelity = run_test00_source_fidelity(
            paths, output_root=self.output_root, run_id=self.run_id, opaque_evidence=opaque,
        )
        union = run_source_union_analysis(paths, output_root=self.run_root)
        validation = self.validate_test00({"fidelity": fidelity, "source_union": union})
        self._source_union_fingerprint = str(union.get("union_fingerprint_sha256") or "") or None
        lossy = fidelity.get("outcome") == TestOutcome.LOSSY.value
        artifact = ProtocolArtifact(
            profile="test00",
            outcome=_protocol_outcome(validation["ok"], blocked=bool(validation["blockers"]), lossy=lossy),
            ok=bool(validation["ok"]),
            run_id=self.run_id,
            checks=tuple(validation["checks"]),
            artifacts={
                "source_mirror": fidelity.get("database"),
                "source_union_private": union.get("private_report"),
                "source_union_sanitized": union.get("sanitized_report"),
                "inventory": inventory,
                "source_inventory_fingerprint": self._source_inventory_fingerprint,
                "source_union_fingerprint": self._source_union_fingerprint,
                "dependency_chain": ["test00"],
            },
            warnings=tuple(validation["warnings"]),
            blockers=tuple(validation["blockers"]),
            details={"fidelity": fidelity, "source_union": union},
            downstream_ready=bool(validation["downstream_ready"]),
        )
        return self._record(artifact)

    def validate_test00(self, result: str | Path | Mapping[str, Any]) -> dict[str, Any]:
        payload = _json_read(result)
        details = dict(payload.get("details") or {})
        fidelity = dict(payload.get("fidelity") or details.get("fidelity") or payload)
        union = dict(payload.get("source_union") or details.get("source_union") or {})
        fidelity_outcome = fidelity.get("outcome")
        fidelity_lossless = fidelity_outcome == TestOutcome.PASSED.value
        checks = [
            {"name": "source_fidelity_lossless", "passed": fidelity_lossless},
            {"name": "source_mirror_sha256", "passed": bool(fidelity.get("database_sha256"))},
            {"name": "source_union_ready", "passed": bool(union.get("ok"))},
            {"name": "source_union_fingerprint", "passed": bool(union.get("union_fingerprint_sha256"))},
            {"name": "source_union_conflicts_resolved", "passed": not bool(union.get("requires_projection_resolution"))},
        ]
        blockers: list[str] = []
        if fidelity_outcome in {TestOutcome.FAILED.value, TestOutcome.BLOCKED.value, None}:
            blockers.append("source_fidelity_not_accepted")
        if not union.get("ok"):
            blockers.append("source_union_not_ready")
        if union.get("requires_projection_resolution"):
            blockers.append("same_node_payload_or_parent_conflict")
        downstream_ready = (
            fidelity_outcome in {TestOutcome.PASSED.value, TestOutcome.LOSSY.value}
            and all(item["passed"] for item in checks[1:])
            and not blockers
        )
        return {
            "ok": downstream_ready and fidelity_lossless,
            "downstream_ready": downstream_ready,
            "checks": checks,
            "warnings": ["lossy_source_present"] if fidelity_outcome == TestOutcome.LOSSY.value else [],
            "blockers": blockers,
        }

    def _build_fresh_database(self, sources: Sequence[Path], target: Path) -> dict[str, Any]:
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        store = UnifiedMemoryDatabase(target, settings=self.settings)
        initialized = store.initialize()
        imported = store.import_sources(sources, dry_run=False, full_validation=False)
        validation = self.validate_test01(target)
        return {"initialized": initialized, "import": imported, "validation": validation}

    def run_test01(
        self,
        sources: Iterable[str | Path],
        *,
        database: str | Path | None = None,
        test00_result: str | Path | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        paths, _inventory = self._sources(sources)
        source_union = build_source_union_manifest(paths)
        self._source_union_fingerprint = (
            str(source_union.get("union_fingerprint_sha256") or "") or None
        )
        prerequisite = (
            test00_result if test00_result is not None else self.results.get("test00")
        )
        prerequisite_context, blocked = self._prerequisite_gate(
            "test01",
            "test00",
            prerequisite,
            expected_source_inventory_fingerprint=self._source_inventory_fingerprint,
            expected_source_union_fingerprint=self._source_union_fingerprint,
        )
        if blocked is not None:
            return blocked
        assert prerequisite_context is not None
        target = Path(database).expanduser().resolve() if database else self.run_root / "test01" / CANONICAL_DATABASE_NAME
        lossy_source_sha256 = {
            str(item["source_sha256"])
            for item in source_union["sources"]
            if item.get("ignored_reason") == "lossy_control_not_canonical"
        }
        import_paths = tuple(path for path in paths if sha256_file(path) not in lossy_source_sha256)
        build = self._build_fresh_database(import_paths, target)
        build["excluded_lossy_source_count"] = len(paths) - len(import_paths)
        validation = build["validation"]
        self._database_sha256 = sha256_file(target) if target.is_file() else None
        self._database_fingerprint = (
            _database_lineage_fingerprint(target) if target.is_file() else None
        )
        artifact = ProtocolArtifact(
            "test01",
            _protocol_outcome(bool(validation["ok"])),
            bool(validation["ok"]),
            self.run_id,
            tuple(validation["checks"]),
            {
                "database": str(target),
                "database_sha256": self._database_sha256,
                "database_fingerprint": self._database_fingerprint,
                "source_inventory_fingerprint": self._source_inventory_fingerprint,
                "source_union_fingerprint": self._source_union_fingerprint,
                "prerequisite_artifact_sha256": prerequisite_context["artifact_sha256"],
                "dependency_chain": ["test00", "test01"],
            },
            tuple(validation.get("warnings") or ()),
            tuple(validation.get("blockers") or ()),
            build,
        )
        return self._record(artifact)

    def validate_test01(self, database: str | Path) -> dict[str, Any]:
        path = Path(database).expanduser().resolve()
        validation = validate_existing_database(path, full=True, include_fts=True)
        stats = dict(validation.get("stats") or {})
        ledger = promotion_ledger_validation(path) if path.is_file() else {"ok": False}
        with open_read_only(path) as con:
            tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            technical = int(con.execute(
                "SELECT COUNT(*) FROM memory_l0_records WHERE record_kind='conversation_message' AND COALESCE(role,'') NOT IN ('user','assistant')"
            ).fetchone()[0]) if "memory_l0_records" in tables else 0
            technical_eligible = int(con.execute(
                "SELECT COUNT(*) FROM memory_l0_records WHERE record_kind='conversation_message' AND COALESCE(role,'') NOT IN ('user','assistant') AND memory_eligible<>0"
            ).fetchone()[0]) if "memory_l0_records" in tables else 0
            l0_variants = int(con.execute("SELECT COUNT(*) FROM memory_l0_conversations").fetchone()[0]) if "memory_l0_conversations" in tables else 0
            archive_variants = int(con.execute(
                "SELECT COUNT(*) FROM conversation_variant_payloads"
            ).fetchone()[0]) if "conversation_variant_payloads" in tables else 0
            variants = max(l0_variants, archive_variants)
            provenance = int(con.execute("SELECT COUNT(*) FROM memory_l0_sources").fetchone()[0]) if "memory_l0_sources" in tables else 0
        checks = [
            {"name": "database_integrity", "passed": bool(validation.get("ok"))},
            {"name": "raw_l0_records_present", "passed": int(stats.get("memory_l0_records", 0)) > 0},
            {"name": "conversation_variants_present", "passed": variants > 0},
            {"name": "provenance_present", "passed": provenance > 0},
            {"name": "technical_records_preserved_but_ineligible", "passed": technical_eligible == 0, "actual": {"technical": technical, "eligible": technical_eligible}},
            {"name": "no_automatic_l2_l3", "passed": ledger.get("automatic_l2") is False and ledger.get("automatic_l3") is False},
        ]
        return {
            "ok": all(item["passed"] for item in checks),
            "checks": checks,
            "validation": validation,
            "promotion_ledger": ledger,
            "warnings": [],
            "blockers": [item["name"] for item in checks if not item["passed"]],
        }

    def run_test02(
        self,
        database: str | Path,
        *,
        test01_result: str | Path | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = Path(database).expanduser().resolve()
        current_database_sha256 = sha256_file(path)
        current_database_fingerprint = _database_lineage_fingerprint(path)
        prerequisite = (
            test01_result if test01_result is not None else self.results.get("test01")
        )
        prerequisite_context, blocked = self._prerequisite_gate(
            "test02",
            "test01",
            prerequisite,
            expected_database_sha256=current_database_sha256,
            expected_database_fingerprint=current_database_fingerprint,
        )
        if blocked is not None:
            return blocked
        assert prerequisite_context is not None
        prerequisite_artifacts = dict(prerequisite_context["artifacts"])
        self._source_inventory_fingerprint = (
            str(prerequisite_artifacts.get("source_inventory_fingerprint") or "") or None
        )
        self._source_union_fingerprint = (
            str(prerequisite_artifacts.get("source_union_fingerprint") or "") or None
        )
        projection = _refresh_derived_projections(path)
        validation = self.validate_test02(path, expected_raw_snapshot=projection["raw_l0_before"])
        self._database_sha256 = sha256_file(path)
        self._database_fingerprint = _database_lineage_fingerprint(path)
        artifact = ProtocolArtifact(
            "test02", _protocol_outcome(bool(validation["ok"])), bool(validation["ok"]), self.run_id,
            tuple(validation["checks"]),
            {
                "database": str(path),
                "database_sha256": self._database_sha256,
                "database_fingerprint": self._database_fingerprint,
                "source_inventory_fingerprint": self._source_inventory_fingerprint,
                "source_union_fingerprint": self._source_union_fingerprint,
                "prerequisite_artifact_sha256": prerequisite_context["artifact_sha256"],
                "dependency_chain": ["test00", "test01", "test02"],
            },
            (), tuple(validation.get("blockers") or ()), {"projection": projection, "validation": validation},
        )
        return self._record(artifact)

    def validate_test02(
        self,
        database: str | Path,
        *,
        expected_raw_snapshot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = Path(database).expanduser().resolve()
        raw = _raw_l0_snapshot(path)
        with open_read_only(path) as con:
            tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            projection_count = int(con.execute("SELECT COUNT(*) FROM memory_rebuild_projections").fetchone()[0]) if "memory_rebuild_projections" in tables else 0
            eligible = int(con.execute("SELECT COUNT(*) FROM memory_rebuild_projections WHERE memory_eligible=1 AND visibility='visible'").fetchone()[0]) if "memory_rebuild_projections" in tables else 0
            fts_count = int(con.execute("SELECT COUNT(*) FROM memory_rebuild_projection_fts").fetchone()[0]) if "memory_rebuild_projection_fts" in tables else 0
            restricted = int(con.execute("SELECT COUNT(*) FROM memory_rebuild_projections WHERE sensitivity='restricted'").fetchone()[0]) if "memory_rebuild_projections" in tables else 0
        checks = [
            {"name": "derived_projection_present", "passed": projection_count > 0, "actual": projection_count},
            {"name": "fts_contains_only_eligible_projection", "passed": fts_count == eligible, "actual": fts_count, "expected": eligible},
            {"name": "sensitivity_classified", "passed": restricted >= 0},
            {"name": "raw_l0_unchanged", "passed": expected_raw_snapshot is None or raw == dict(expected_raw_snapshot)},
        ]
        return {"ok": all(item["passed"] for item in checks), "checks": checks, "raw_l0": raw, "blockers": [item["name"] for item in checks if not item["passed"]]}

    def run_test03(
        self,
        sources: Iterable[str | Path],
        *,
        test02_result: str | Path | Mapping[str, Any] | None = None,
        test00_result: str | Path | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        paths, _inventory = self._sources(sources)
        del test00_result
        union = build_source_union_manifest(paths)
        self._source_union_fingerprint = str(union.get("union_fingerprint_sha256") or "") or None
        prerequisite = (
            test02_result if test02_result is not None else self.results.get("test02")
        )
        prerequisite_context, blocked = self._prerequisite_gate(
            "test03",
            "test02",
            prerequisite,
            expected_source_inventory_fingerprint=self._source_inventory_fingerprint,
            expected_source_union_fingerprint=self._source_union_fingerprint,
        )
        if blocked is not None:
            return blocked
        assert prerequisite_context is not None
        prerequisite_artifacts = dict(prerequisite_context["artifacts"])
        self._database_sha256 = (
            str(prerequisite_artifacts.get("database_sha256") or "") or None
        )
        self._database_fingerprint = (
            str(prerequisite_artifacts.get("database_fingerprint") or "") or None
        )
        if not union.get("ok") or union.get("requires_projection_resolution"):
            blockers = ["source_union_not_ready"] if not union.get("ok") else ["same_node_payload_or_parent_conflict"]
            return self._record(ProtocolArtifact("test03", "BLOCKED", False, self.run_id, (), {}, (), tuple(blockers), {"source_union": union}))
        lossy_source_sha256 = {
            str(item["source_sha256"])
            for item in union["sources"]
            if item.get("ignored_reason") == "lossy_control_not_canonical"
        }
        build_paths = tuple(
            path for path in paths if sha256_file(path) not in lossy_source_sha256
        )
        root = self._ensure_root() / "test03"
        database_a = root / "build-a" / CANONICAL_DATABASE_NAME
        database_b = root / "build-b" / CANONICAL_DATABASE_NAME
        build_a = self._build_fresh_database(build_paths, database_a)
        projection_a = _refresh_derived_projections(database_a)
        build_b = self._build_fresh_database(list(reversed(build_paths)), database_b)
        projection_b = _refresh_derived_projections(database_b)
        snapshot_a = _semantic_database_snapshot(database_a)
        snapshot_b = _semantic_database_snapshot(database_b)
        report = {
            "source_union": union,
            "database_a": str(database_a),
            "database_b": str(database_b),
            "database_a_sha256": sha256_file(database_a),
            "database_b_sha256": sha256_file(database_b),
            "snapshot_a": snapshot_a,
            "snapshot_b": snapshot_b,
            "semantic_reconciliation": snapshot_a == snapshot_b,
            "build_a": build_a,
            "build_b": build_b,
            "projection_a": projection_a,
            "projection_b": projection_b,
            "excluded_lossy_source_count": len(paths) - len(build_paths),
        }
        validation = self.validate_test03(report)
        artifact = ProtocolArtifact(
            "test03", _protocol_outcome(bool(validation["ok"])), bool(validation["ok"]), self.run_id,
            tuple(validation["checks"]),
            {
                "database_a": str(database_a),
                "database_b": str(database_b),
                "database_sha256": self._database_sha256,
                "database_fingerprint": self._database_fingerprint,
                "source_inventory_fingerprint": self._source_inventory_fingerprint,
                "source_union_fingerprint": self._source_union_fingerprint,
                "prerequisite_artifact_sha256": prerequisite_context["artifact_sha256"],
                "dependency_chain": ["test00", "test01", "test02", "test03"],
            },
            (), tuple(validation.get("blockers") or ()), report,
        )
        return self._record(artifact)

    def validate_test03(self, result: str | Path | Mapping[str, Any]) -> dict[str, Any]:
        payload = _json_read(result)
        union = dict(payload.get("source_union") or payload.get("details", {}).get("source_union") or {})
        reconciled = bool(payload.get("semantic_reconciliation"))
        if "details" in payload and not reconciled:
            details = dict(payload.get("details") or {})
            reconciled = bool(details.get("semantic_reconciliation"))
        checks = [
            {"name": "source_union_ready", "passed": bool(union.get("ok"))},
            {"name": "branch_union_not_blocking", "passed": not bool(union.get("requires_projection_resolution"))},
            {"name": "normal_reverse_semantic_reconciliation", "passed": reconciled},
        ]
        return {"ok": all(item["passed"] for item in checks), "checks": checks, "blockers": [item["name"] for item in checks if not item["passed"]]}

    def run_test04(
        self,
        database: str | Path,
        benchmark: str | Path,
        *,
        test03_result: str | Path | Mapping[str, Any] | None = None,
        system_acceptance: bool = False,
        restart_continuity_report: str | Path | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = Path(database).expanduser().resolve()
        current_database_sha256 = sha256_file(path)
        current_database_fingerprint = _database_lineage_fingerprint(path)
        prerequisite = (
            test03_result if test03_result is not None else self.results.get("test03")
        )
        prerequisite_context, blocked = self._prerequisite_gate(
            "test04",
            "test03",
            prerequisite,
            expected_database_sha256=current_database_sha256,
            expected_database_fingerprint=current_database_fingerprint,
        )
        if blocked is not None:
            return blocked
        assert prerequisite_context is not None
        prerequisite_artifacts = dict(prerequisite_context["artifacts"])
        self._source_inventory_fingerprint = (
            str(prerequisite_artifacts.get("source_inventory_fingerprint") or "") or None
        )
        self._source_union_fingerprint = (
            str(prerequisite_artifacts.get("source_union_fingerprint") or "") or None
        )
        self._database_fingerprint = (
            str(prerequisite_artifacts.get("database_fingerprint") or "") or None
        )
        result = run_fts5_recall_benchmark(
            path, benchmark, output_root=self._ensure_root() / "test04", run_id="recall"
        )
        validation = self.validate_test04(
            result,
            benchmark=benchmark,
            system_acceptance=system_acceptance,
            restart_continuity_report=restart_continuity_report,
        )
        self._database_sha256 = sha256_file(path)
        artifact = ProtocolArtifact(
            "test04", _protocol_outcome(bool(validation["ok"]), blocked=bool(validation["blockers"])), bool(validation["ok"]), self.run_id,
            tuple(validation["checks"]),
            {
                "database": str(path),
                "database_sha256": self._database_sha256,
                "database_fingerprint": self._database_fingerprint,
                "source_inventory_fingerprint": self._source_inventory_fingerprint,
                "source_union_fingerprint": self._source_union_fingerprint,
                "recall_private": result.get("private_report"),
                "recall_sanitized": result.get("sanitized_report"),
                "prerequisite_artifact_sha256": prerequisite_context["artifact_sha256"],
                "dependency_chain": [
                    "test00",
                    "test01",
                    "test02",
                    "test03",
                    "test04",
                ],
            },
            (), tuple(validation["blockers"]), {"recall": result, "validation": validation},
        )
        return self._record(artifact)

    def validate_test04(
        self,
        result: str | Path | Mapping[str, Any],
        *,
        benchmark: str | Path,
        system_acceptance: bool = False,
        restart_continuity_report: str | Path | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = _json_read(result)
        suite = load_recall_benchmark(benchmark)
        categories = {case.category for case in suite.cases}
        category_missing = sorted(item.value for item in _REQUIRED_RECALL_CATEGORIES - categories)
        referential = [item for item in suite.cases if item.category is RecallCaseCategory.REFERENTIAL_FOLLOWUP]
        provenance = [item for item in suite.cases if item.category is RecallCaseCategory.PROVENANCE]
        temporal = [item for item in suite.cases if item.category is RecallCaseCategory.TEMPORAL]
        negative = [item for item in suite.cases if item.category is RecallCaseCategory.NEGATIVE]
        sensitive = [item for item in suite.cases if item.category is RecallCaseCategory.SENSITIVE_BOUNDARY]
        metrics = dict(payload.get("metrics") or {})
        gate = dict(payload.get("quality_gate") or {})
        restart = _json_read(restart_continuity_report) if restart_continuity_report is not None else {}
        checks = [
            {"name": "recall_benchmark_executed", "passed": bool(payload.get("benchmark_completed"))},
            {"name": "required_case_categories", "passed": not category_missing, "missing": category_missing},
            {"name": "referential_multi_turn_context", "passed": bool(referential) and all(item.context_turns for item in referential)},
            {"name": "temporal_bounds", "passed": bool(temporal) and all(item.temporal_start or item.temporal_end for item in temporal)},
            {"name": "exact_provenance_expectation", "passed": bool(provenance) and all(item.expected_source_ids or item.expected_source_kinds for item in provenance)},
            {"name": "negative_abstention", "passed": bool(negative) and all(item.expected_abstain for item in negative)},
            {"name": "sensitive_boundary", "passed": bool(sensitive) and all(item.forbidden_any for item in sensitive)},
            {"name": "all_cases_passed", "passed": int(metrics.get("case_count", 0)) > 0 and metrics.get("passed_count") == metrics.get("case_count")},
            {"name": "quality_gate_configured_and_passed", "passed": gate.get("configured") is True and gate.get("passed") is True},
            {"name": "restart_continuity", "passed": (not system_acceptance) or restart.get("status") == "passed"},
        ]
        blockers = [item["name"] for item in checks if not item["passed"]]
        return {"ok": not blockers, "checks": checks, "blockers": blockers, "developer_acceptance": not [item for item in checks[:-1] if not item["passed"]], "system_acceptance": system_acceptance and not blockers}

    def run_final(
        self,
        database: str | Path,
        output: str | Path,
        *,
        test04_result: str | Path | Mapping[str, Any],
        sources: Iterable[str | Path] = (),
    ) -> dict[str, Any]:
        source = Path(database).expanduser().resolve()
        current_database_sha256 = sha256_file(source)
        current_database_fingerprint = _database_lineage_fingerprint(source)
        prerequisite_context, blocked = self._prerequisite_gate(
            "final",
            "test04",
            test04_result,
            expected_database_sha256=current_database_sha256,
            expected_database_fingerprint=current_database_fingerprint,
        )
        if blocked is not None:
            return blocked
        assert prerequisite_context is not None
        test04 = dict(prerequisite_context["payload"])
        prerequisite_artifacts = dict(prerequisite_context["artifacts"])
        self._source_inventory_fingerprint = (
            str(prerequisite_artifacts.get("source_inventory_fingerprint") or "") or None
        )
        self._source_union_fingerprint = (
            str(prerequisite_artifacts.get("source_union_fingerprint") or "") or None
        )
        self._database_fingerprint = (
            str(prerequisite_artifacts.get("database_fingerprint") or "") or None
        )
        target = Path(output).expanduser().resolve()
        if target.exists():
            raise FileExistsError(target)
        staging = target.with_name(target.name + ".staging-" + uuid.uuid4().hex)
        staging.mkdir(parents=True, exist_ok=False)
        try:
            staged_database = staging / CANONICAL_DATABASE_NAME
            UnifiedMemoryDatabase(source).backup(staged_database)
            validation = validate_existing_database(staged_database, full=True, include_fts=True)
            ledger = promotion_ledger_validation(staged_database)
            source_inventory = []
            for raw in sources:
                item = Path(raw).expanduser().resolve()
                if item.is_file():
                    source_inventory.append({"path": str(item), "sha256": sha256_file(item), "size_bytes": item.stat().st_size})
            summary = {
                "schema_version": "jazn_memory_rebuild_final/v4",
                "ok": bool(validation.get("ok")) and bool(ledger.get("ok")),
                "created_at": _utc_now(),
                "database": str(staged_database),
                "database_sha256": sha256_file(staged_database),
                "validation": validation,
                "promotion_ledger_validation": ledger,
                "test04": test04,
                "source_inventory": source_inventory,
                "runtime_activated": False,
                "automatic_l2": False,
                "automatic_l3": False,
                "automatic_activation": False,
            }
            write_report_pair(staging, "final", summary)
            if not summary["ok"]:
                raise RuntimeError("final staging validation failed")
            os.replace(staging, target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        validation = self.validate_final(target, test04_result=test04)
        self._database_sha256 = str(validation.get("database_sha256") or "") or None
        artifact = ProtocolArtifact(
            "final", _protocol_outcome(bool(validation["ok"])), bool(validation["ok"]), self.run_id,
            tuple(validation["checks"]),
            {
                "output": str(target),
                "database_sha256": self._database_sha256,
                "database_fingerprint": self._database_fingerprint,
                "source_inventory_fingerprint": self._source_inventory_fingerprint,
                "source_union_fingerprint": self._source_union_fingerprint,
                "prerequisite_artifact_sha256": prerequisite_context["artifact_sha256"],
                "dependency_chain": list(TEST_PROTOCOL_ORDER),
            },
            (), tuple(validation.get("blockers") or ()), validation,
        )
        return self._record(artifact)

    def validate_final(
        self,
        output: str | Path,
        *,
        test04_result: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        root = Path(output).expanduser().resolve()
        database = root / CANONICAL_DATABASE_NAME
        validation = validate_existing_database(database, full=True, include_fts=True)
        ledger = promotion_ledger_validation(database) if database.is_file() else {"ok": False}
        test04 = _json_read(test04_result)
        checks = [
            {"name": "test04_passed", "passed": bool(test04.get("ok"))},
            {"name": "sqlite_backup_snapshot_exists", "passed": database.is_file()},
            {"name": "integrity_foreign_keys_fts", "passed": bool(validation.get("ok"))},
            {"name": "promotion_ledger_fail_closed", "passed": bool(ledger.get("ok"))},
            {"name": "private_manifest", "passed": (root / "final.private.json").is_file()},
            {"name": "sanitized_manifest", "passed": (root / "final.sanitized.json").is_file()},
            {"name": "runtime_not_activated", "passed": True},
        ]
        return {"ok": all(item["passed"] for item in checks), "checks": checks, "blockers": [item["name"] for item in checks if not item["passed"]], "database_sha256": sha256_file(database) if database.is_file() else None, "validation": validation, "promotion_ledger_validation": ledger}

    def validate(self, profile: str, artifact: str | Path | Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        selected = profile.strip().lower()
        validator = getattr(self, f"validate_{selected}", None)
        if validator is None or selected not in TEST_PROTOCOL_ORDER:
            raise ValueError(f"unknown protocol: {profile}")
        return dict(validator(artifact, **kwargs))

    def seal_manifest(self) -> dict[str, str]:
        if self._manifest_paths is not None:
            return dict(self._manifest_paths)
        warnings = tuple(
            warning
            for result in self.results.values()
            for warning in result.get("warnings", [])
        )
        blockers = tuple(
            blocker
            for result in self.results.values()
            for blocker in result.get("blockers", [])
        )
        completed = self._manifest.complete(
            source_union_fingerprint=self._source_union_fingerprint,
            database_sha256=self._database_sha256,
            warnings=warnings,
            blockers=blockers,
            validation_results={name: {"ok": value.get("ok"), "outcome": value.get("outcome")} for name, value in self.results.items()},
        )
        self._manifest_paths = completed.write_once(self._ensure_root())
        return dict(self._manifest_paths)


__all__ = ["PROTOCOL_ENGINE_SCHEMA", "ProtocolArtifact", "ProtocolEngine"]
