from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import sqlite3

from .read_only_validation import (
    open_read_only,
    promotion_ledger_validation,
    validate_existing_database,
)
from .unified_memory import CANONICAL_DATABASE_NAME
from .test_spec import get_test_spec
from .unified_schema import quote

PROFILE_NAMES = ("test01", "test02", "test03", "test04", "final")
_COMPARE_TABLES = (
    "conversations", "nodes", "fts_docs", "journal_entries",
    "candidates", "experiences", "memory_records",
    "memory_l0_sources", "memory_l0_records", "memory_l0_occurrences",
    "memory_l0_affect_claims",
)
_SEMANTIC_FINGERPRINT_TABLES = tuple(dict.fromkeys((
    *_COMPARE_TABLES,
    "import_sources",
    "import_source_aliases",
    "conversation_occurrences",
    "conversation_revisions",
    "conversation_variant_payloads",
    "import_conflicts",
    "journal_sources",
    "journal_entry_sources",
    "journal_revisions",
    "experience_domains",
    "experience_sources",
    "memory_evidence",
    "working_memory_index",
    "short_term_memory_index",
    "promotion_requests",
    "promotion_decisions",
    "long_term_memory_index",
    "sources",
    "source_occurrences",
    "links",
    "verifications",
    "memory_l0_sources",
    "memory_l0_records",
    "memory_l0_occurrences",
    "memory_l0_assets",
    "memory_l0_record_assets",
    "memory_l0_affect_claims",
    "memory_l0_conversations",
    "memory_rebuild_projections",
    "candidate_revisions",
    "candidate_evidence",
    "candidate_links",
    "promotion_ledger",
    "unified_migration_conflicts",
    "runtime_memory_import_conflicts",
)))
_REQUIRED_TEST04_FIELDS = (
    "structural_integrity", "source_completeness", "same_target_idempotence",
    "fresh_rebuild_reproducibility", "test03_reconciliation", "recall",
    "multi_turn_review",
)
_VOLATILE_RECONCILIATION_COLUMNS = frozenset({
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
    "first_seen_import_id",
    "last_seen_import_id",
    "import_id",
})


def _check(name: str, passed: bool, *, actual: Any = None, expected: Any = None,
           blocking: bool = True, detail: str = "") -> dict[str, Any]:
    return {
        "name": name, "passed": bool(passed), "blocking": bool(blocking),
        "actual": actual, "expected": expected, "detail": detail,
    }


def _baseline_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        if root.suffix.casefold() not in {".sqlite", ".sqlite3", ".db"}:
            raise ValueError(f"baseline is not SQLite: {root}")
        return [root]
    names = {
        "archive_chats.sqlite3", "journal.sqlite3", "experience.sqlite3",
        "memory_jazn.sqlite3", "import_catalog.sqlite3",
    }
    files = [path.resolve() for path in root.rglob("*.sqlite3") if path.name in names]
    if not files:
        raise FileNotFoundError(f"baseline contains no recognized SQLite databases: {root}")
    return files


def _pk_columns(con: sqlite3.Connection, table: str) -> list[str]:
    rows = list(con.execute(f"PRAGMA table_info({quote(table)})"))
    return [str(row[1]) for row in sorted((row for row in rows if int(row[5]) > 0), key=lambda row: int(row[5]))]


def _table_columns(path: Path, table: str) -> tuple[list[str], list[str]]:
    with open_read_only(path) as con:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            return [], []
        info = list(con.execute(f"PRAGMA table_info({quote(table)})"))
        columns = [str(row[1]) for row in info]
        pk = [
            str(row[1])
            for row in sorted(
                (row for row in info if int(row[5]) > 0),
                key=lambda row: int(row[5]),
            )
        ]
        return columns, pk


def _projected_record_hashes(
    path: Path,
    table: str,
    *,
    columns: list[str],
    key_columns: list[str],
) -> dict[str, set[str]]:
    if not columns:
        return {}
    selected = ",".join(quote(item) for item in columns)
    key_indexes = [columns.index(item) for item in key_columns]
    result: dict[str, set[str]] = {}
    with open_read_only(path) as con:
        for row in con.execute(f"SELECT {selected} FROM {quote(table)}"):
            values = list(row)
            key_payload = [values[index] for index in key_indexes]
            content_payload = dict(zip(columns, values))
            key_encoded = json.dumps(
                key_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            content_encoded = json.dumps(
                content_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            key_hash = hashlib.sha256(key_encoded.encode("utf-8")).hexdigest()
            content_hash = hashlib.sha256(content_encoded.encode("utf-8")).hexdigest()
            result.setdefault(key_hash, set()).add(content_hash)
    return result


def _stable_record_hashes(path: Path, table: str) -> dict[str, set[str]]:
    """Return stable-key -> content-hash variants for one table.

    Reconciliation must detect the important case where a primary key survives
    but its payload changes.  Multiple baseline databases may legitimately
    contain different historical variants of one key, so values are sets.
    """

    with open_read_only(path) as con:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            return {}
        info = list(con.execute(f"PRAGMA table_info({quote(table)})"))
        columns = [str(row[1]) for row in info]
        if not columns:
            return {}
        pk = _pk_columns(con, table)
        key_columns = pk or columns
        content_columns = [
            column
            for column in columns
            if column not in _VOLATILE_RECONCILIATION_COLUMNS
            or column in key_columns
        ]
        selected = ",".join(quote(item) for item in columns)
        key_indexes = [columns.index(item) for item in key_columns]
        content_indexes = [columns.index(item) for item in content_columns]
        result: dict[str, set[str]] = {}
        for row in con.execute(f"SELECT {selected} FROM {quote(table)}"):
            values = list(row)
            key_payload = [values[index] for index in key_indexes]
            content_payload = {
                column: values[index]
                for column, index in zip(content_columns, content_indexes)
            }
            key_encoded = json.dumps(
                key_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            content_encoded = json.dumps(
                content_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            key_hash = hashlib.sha256(key_encoded.encode("utf-8")).hexdigest()
            content_hash = hashlib.sha256(content_encoded.encode("utf-8")).hexdigest()
            result.setdefault(key_hash, set()).add(content_hash)
        return result


def semantic_database_fingerprint(database: str | Path) -> str:
    """Fingerprint stable memory content while intentionally excluding metadata.

    This avoids a self-reference loop: acceptance evidence is stored in
    unified_memory_meta, but the evidence must still be bound to the actual
    candidate memory content it accepted.
    """

    path = Path(database).expanduser().resolve()
    payload: dict[str, dict[str, list[str]]] = {}
    for table in _SEMANTIC_FINGERPRINT_TABLES:
        records = _stable_record_hashes(path, table)
        if records:
            payload[table] = {
                key: sorted(values)
                for key, values in sorted(records.items())
            }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def baseline_record_reconciliation(database: str | Path, roots: Iterable[str | Path]) -> dict[str, Any]:
    target = Path(database).expanduser().resolve()
    roots = list(roots)
    if not roots:
        return {"ok": False, "reason": "baseline_required", "tables": {}}
    baseline_sets: dict[str, dict[str, set[str]]] = {
        table: {} for table in _COMPARE_TABLES
    }
    target_sets: dict[str, dict[str, set[str]]] = {
        table: {} for table in _COMPARE_TABLES
    }
    projection_details: dict[str, list[dict[str, Any]]] = {
        table: [] for table in _COMPARE_TABLES
    }
    files: list[Path] = []
    try:
        for raw in roots:
            files.extend(_baseline_files(Path(raw).expanduser().resolve()))
        for source in files:
            for table in _COMPARE_TABLES:
                source_columns, source_pk = _table_columns(source, table)
                target_columns, target_pk = _table_columns(target, table)
                if not source_columns or not target_columns:
                    continue
                key_columns = [
                    item
                    for item in source_pk
                    if item in target_columns
                ]
                if not key_columns:
                    key_columns = [
                        item
                        for item in target_pk
                        if item in source_columns
                    ]
                shared_columns = [
                    item
                    for item in target_columns
                    if item in source_columns
                    and (
                        item not in _VOLATILE_RECONCILIATION_COLUMNS
                        or item in key_columns
                    )
                ]
                if not key_columns:
                    key_columns = list(shared_columns)
                for key_column in key_columns:
                    if key_column not in shared_columns:
                        shared_columns.insert(0, key_column)
                if not shared_columns or not key_columns:
                    continue

                baseline_records = _projected_record_hashes(
                    source,
                    table,
                    columns=shared_columns,
                    key_columns=key_columns,
                )
                target_records = _projected_record_hashes(
                    target,
                    table,
                    columns=shared_columns,
                    key_columns=key_columns,
                )
                for key_hash, content_hashes in baseline_records.items():
                    baseline_sets[table].setdefault(key_hash, set()).update(content_hashes)
                for key_hash, content_hashes in target_records.items():
                    target_sets[table].setdefault(key_hash, set()).update(content_hashes)
                projection_details[table].append(
                    {
                        "baseline_database": source.name,
                        "shared_columns": shared_columns,
                        "key_columns": key_columns,
                    }
                )

        tables: dict[str, Any] = {}
        ok = True
        for table in _COMPARE_TABLES:
            target_records = target_sets[table]
            baseline_records = baseline_sets[table]
            baseline_keys = set(baseline_records)
            target_keys = set(target_records)
            missing = baseline_keys - target_keys
            changed = {
                key
                for key in baseline_keys & target_keys
                if baseline_records[key].isdisjoint(target_records[key])
            }
            tables[table] = {
                "baseline_record_count": len(baseline_keys),
                "target_record_count": len(target_keys),
                "missing_record_count": len(missing),
                "content_mismatch_count": len(changed),
                "missing_record_key_sha256_samples": sorted(missing)[:25],
                "content_mismatch_key_sha256_samples": sorted(changed)[:25],
                "projections": projection_details[table],
            }
            if missing or changed:
                ok = False
        return {
            "ok": ok,
            "baseline_database_count": len(files),
            "tables": tables,
            "comparison": "shared_stable_columns_primary_key_and_content_hash_presence",
            "private_paths_persisted": False,
        }
    except (OSError, sqlite3.DatabaseError, ValueError) as exc:
        return {
            "ok": False, "reason": "baseline_read_error",
            "error_type": type(exc).__name__, "error": str(exc), "tables": {},
        }


def _affect_evidence_integrity(path: Path) -> dict[str, Any]:
    """Verify that derived affect claims are an exact projection of RAW L0 evidence."""

    if not path.is_file():
        return {"ok": False, "reason": "database_missing"}
    try:
        with open_read_only(path) as con:
            tables = {
                str(row[0])
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "memory_l0_records" not in tables:
                return {
                    "ok": True,
                    "status": "not_applicable_no_l0",
                    "expected_claim_count": 0,
                    "actual_claim_count": 0,
                    "missing_claim_count": 0,
                    "unexpected_claim_count": 0,
                }

            expected: set[tuple[str, str, str, str, str]] = set()
            invalid_raw: list[str] = []
            rows = con.execute(
                "SELECT record_id,raw_json FROM memory_l0_records "
                "WHERE is_current_revision=1 "
                "AND source_kind IN ('journal','music_analysis','affective')"
            ).fetchall()
            for row in rows:
                record_id = str(row["record_id"])
                try:
                    raw = json.loads(str(row["raw_json"] or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    invalid_raw.append(record_id)
                    continue
                if not isinstance(raw, dict):
                    continue
                claims = raw.get("__jazn_affect_claims__")
                if not isinstance(claims, list):
                    continue
                for claim in claims:
                    if not isinstance(claim, dict):
                        continue
                    label = str(claim.get("label") or "").strip()
                    if not label:
                        continue
                    normalized = " ".join(label.casefold().split())
                    source_field = str(
                        claim.get("source_field") or "unknown"
                    ).strip() or "unknown"
                    claim_kind = str(
                        claim.get("claim_kind") or "explicit_source_label"
                    ).strip()
                    subject = str(claim.get("subject") or "latka").strip() or "latka"
                    expected.add(
                        (record_id, normalized, source_field, claim_kind, subject)
                    )

            actual: set[tuple[str, str, str, str, str]] = set()
            invalid_boundaries: list[str] = []
            if "memory_l0_affect_claims" in tables:
                claim_rows = con.execute(
                    "SELECT c.claim_id,c.record_id,c.normalized_label,c.source_field,"
                    "c.claim_kind,c.subject,c.boundary "
                    "FROM memory_l0_affect_claims AS c "
                    "JOIN memory_l0_records AS r ON r.record_id=c.record_id "
                    "WHERE r.is_current_revision=1 "
                    "AND r.source_kind IN ('journal','music_analysis','affective')"
                ).fetchall()
                for claim in claim_rows:
                    actual.add((
                        str(claim["record_id"]),
                        str(claim["normalized_label"]),
                        str(claim["source_field"]),
                        str(claim["claim_kind"]),
                        str(claim["subject"]),
                    ))
                    if str(claim["boundary"]) != (
                        "source_claimed_affect_not_biological_state"
                    ):
                        invalid_boundaries.append(str(claim["claim_id"]))

            missing = expected - actual
            unexpected = actual - expected
            return {
                "ok": not invalid_raw
                and not missing
                and not unexpected
                and not invalid_boundaries,
                "status": "checked",
                "expected_claim_count": len(expected),
                "actual_claim_count": len(actual),
                "missing_claim_count": len(missing),
                "unexpected_claim_count": len(unexpected),
                "invalid_raw_record_count": len(invalid_raw),
                "invalid_boundary_count": len(invalid_boundaries),
                "missing_claim_samples": sorted(missing)[:25],
                "unexpected_claim_samples": sorted(unexpected)[:25],
                "invalid_raw_record_samples": sorted(invalid_raw)[:25],
                "invalid_boundary_claim_samples": sorted(invalid_boundaries)[:25],
                "truth_boundary": "source_claimed_affect_not_biological_state",
                "derived_projection_only": True,
            }
    except (OSError, sqlite3.DatabaseError, ValueError) as exc:
        return {
            "ok": False,
            "reason": "affect_evidence_integrity_error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _unresolved_conflicts(path: Path) -> dict[str, int]:
    with open_read_only(path) as con:
        tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        chat_conflicts = 0
        preserved_chat_divergences = 0
        if "import_conflicts" in tables:
            columns = {str(row[1]) for row in con.execute("PRAGMA table_info(import_conflicts)")}
            if "resolution_status" in columns:
                chat_conflicts = int(con.execute(
                    "SELECT COUNT(*) FROM import_conflicts "
                    "WHERE COALESCE(resolution_status,'unresolved')='unresolved'"
                ).fetchone()[0])
                preserved_chat_divergences = int(con.execute(
                    "SELECT COUNT(*) FROM import_conflicts WHERE resolution_status='preserved_union'"
                ).fetchone()[0])
            else:
                chat_conflicts = int(con.execute("SELECT COUNT(*) FROM import_conflicts").fetchone()[0])
        result = {
            "chat_import_conflicts": chat_conflicts,
            "migration_conflicts": int(con.execute("SELECT COUNT(*) FROM unified_migration_conflicts WHERE status='unresolved'").fetchone()[0]) if "unified_migration_conflicts" in tables else 0,
            "runtime_sync_conflicts": int(con.execute("SELECT COUNT(*) FROM runtime_memory_import_conflicts WHERE status='unresolved'").fetchone()[0]) if "runtime_memory_import_conflicts" in tables else 0,
        }
        result["total"] = sum(result.values())
        result["preserved_chat_divergences"] = preserved_chat_divergences
        return result


def _load_acceptance_report(
    path: str | Path | None,
    *,
    expected_database_fingerprint: str | None = None,
    expected_source_union_sha256: str | None = None,
    expected_restore_run_id: str | None = None,
    expected_protocol_run_id: str | None = None,
) -> dict[str, Any]:
    if path is None:
        return {"ok": False, "reason": "full_test04_acceptance_report_required"}
    report_path = Path(path).expanduser().resolve()
    if not report_path.is_file():
        return {"ok": False, "reason": "acceptance_report_missing"}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": "acceptance_report_invalid", "error": str(exc)}
    final = payload.get("final") if isinstance(payload, dict) else None
    if not isinstance(final, dict):
        return {"ok": False, "reason": "acceptance_report_has_no_final_block"}
    required = {field: final.get(field) for field in _REQUIRED_TEST04_FIELDS}
    html = final.get("html_import_dry_run", "not_applicable")
    restart = final.get("restart_continuity", "not_run")
    required_ok = all(value == "passed" for value in required.values())
    html_ok = html in {"passed", "not_applicable"}

    binding = payload.get("binding") if isinstance(payload, dict) else None
    binding_payload = dict(binding) if isinstance(binding, dict) else {}
    expected_binding = {
        "database_semantic_fingerprint": expected_database_fingerprint,
        "source_union_sha256": expected_source_union_sha256,
        "restore_run_id": expected_restore_run_id,
        "protocol_run_id": expected_protocol_run_id,
    }
    binding_checks = {
        key: {
            "required": bool(expected),
            "expected": expected,
            "actual": binding_payload.get(key),
            "passed": (not expected) or binding_payload.get(key) == expected,
        }
        for key, expected in expected_binding.items()
    }
    binding_required = any(bool(value) for value in (
        expected_source_union_sha256,
        expected_restore_run_id,
        expected_protocol_run_id,
    ))
    if binding_required:
        binding_ok = (
            bool(binding_payload)
            and bool(expected_database_fingerprint)
            and all(item["passed"] for item in binding_checks.values())
        )
    else:
        # Compatibility path for old developer fixtures that predate bound
        # canonical Studio candidates. Canonical reconstructed databases always
        # carry restore/source/protocol lineage and therefore require binding.
        binding_ok = True

    return {
        "ok": required_ok and html_ok and binding_ok,
        "required": required,
        "html_import_dry_run": html,
        "restart_continuity": restart,
        "system_acceptance_restart_passed": restart == "passed",
        "binding_required": binding_required,
        "binding_ok": binding_ok,
        "binding": binding_payload,
        "binding_checks": binding_checks,
        "source": "memory_sqlite_test04",
    }


def run_test_profile(
    database: str | Path,
    profile: str,
    *,
    baselines: Iterable[str | Path] = (),
    full_validation: bool = True,
    acceptance_report: str | Path | None = None,
    system_acceptance: bool = False,
) -> dict[str, Any]:
    selected = profile.strip().lower()
    if selected not in PROFILE_NAMES:
        raise ValueError(f"Nieznany profil {profile!r}. Dozwolone: {', '.join(PROFILE_NAMES)}")
    spec = get_test_spec(selected)
    path = Path(database).expanduser().resolve()
    before = path.stat().st_mtime_ns if path.is_file() else None
    validation = validate_existing_database(path, full=full_validation, include_fts=True)
    stats = validation.get("stats") or {}
    fts = validation.get("fts") or {}
    checks: list[dict[str, Any]] = [
        _check("database_exists_and_read_only_validation", validation.get("reason") != "database_missing", actual=validation.get("reason"), expected="existing database"),
        _check("sqlite_integrity_and_foreign_keys", bool(validation.get("ok")), actual={
            "integrity": validation.get("integrity"), "foreign_key_error_count": validation.get("foreign_key_error_count")
        }),
        _check("single_physical_database", validation.get("single_physical_database") is True, actual=validation.get("legacy_sibling_databases"), expected=[]),
        _check("fts_integrity_and_smoke", bool(fts.get("ok")), actual=fts, expected="all present FTS indexes integrity-check + smoke query pass"),
        _check("conversations_present", int(stats.get("conversations", 0)) > 0, actual=stats.get("conversations", 0), expected=">0"),
        _check("nodes_present", int(stats.get("nodes", 0)) > 0, actual=stats.get("nodes", 0), expected=">0"),
        _check("conversation_search_index_present", int(stats.get("fts_docs", 0)) > 0, actual=stats.get("fts_docs", 0), expected=">0"),
    ]
    if selected in {"test02", "test03", "test04", "final"}:
        checks.append(_check("journal_present", int(stats.get("journal_entries", 0)) > 0, actual=stats.get("journal_entries", 0), expected=">0"))
    conflicts = _unresolved_conflicts(path) if path.is_file() else {"total": 1}
    if selected in {"test03", "test04", "final"}:
        checks.extend((
            _check("import_provenance_present", int(stats.get("import_sources", 0)) > 0, actual=stats.get("import_sources", 0), expected=">0"),
            _check("no_unresolved_import_or_migration_conflicts", conflicts.get("total", 0) == 0, actual=conflicts, expected={"total": 0}),
        ))
    reconciliation = {"ok": True, "status": "not_required"}
    acceptance = {"ok": True, "status": "not_required"}
    if selected in {"test04", "final"}:
        reconciliation = baseline_record_reconciliation(path, baselines)
        checks.append(_check(
            "test03_record_level_reconciliation", bool(reconciliation.get("ok")),
            actual=reconciliation, expected="baseline required and no missing stable keys or content mismatches",
        ))
        affect_integrity = _affect_evidence_integrity(path)
        checks.append(_check(
            "affect_evidence_projection_integrity",
            bool(affect_integrity.get("ok")),
            actual=affect_integrity,
            expected=(
                "every explicit RAW L0 affect claim is represented exactly once "
                "with source_claimed_affect_not_biological_state boundary"
            ),
        ))
        unified_meta: dict[str, str] = {}
        if path.is_file():
            with open_read_only(path) as con:
                tables = {
                    str(row[0])
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if "unified_memory_meta" in tables:
                    unified_meta = {
                        str(row[0]): str(row[1])
                        for row in con.execute(
                            "SELECT key,value FROM unified_memory_meta"
                        )
                    }
        acceptance = _load_acceptance_report(
            acceptance_report,
            expected_database_fingerprint=(
                semantic_database_fingerprint(path) if path.is_file() else None
            ),
            expected_source_union_sha256=(
                unified_meta.get("source_union_sha256") or None
            ),
            expected_restore_run_id=unified_meta.get("restore_run_id") or None,
            expected_protocol_run_id=unified_meta.get("protocol_run_id") or None,
        )
        acceptance_ok = bool(acceptance.get("ok"))
        if system_acceptance:
            acceptance_ok = acceptance_ok and bool(acceptance.get("system_acceptance_restart_passed"))
        checks.append(_check(
            "full_test04_acceptance", acceptance_ok, actual=acceptance,
            expected=(
                "passed: source completeness, idempotence, fresh rebuild, Test03 reconciliation, recall, "
                "multi-turn, HTML dry-run when applicable; restart/wake-state additionally for system acceptance"
            ),
            detail="system_acceptance=true requires restart_continuity=passed" if system_acceptance else "developer acceptance",
        ))
    ledger = {"ok": True, "status": "not_required"}
    runtime_probe: dict[str, Any] = {"status": "not_required"}
    if selected == "final" and path.is_file():
        from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database

        runtime_probe = probe_unified_memory_database(path, full_integrity=full_validation)
        checks.append(_check(
            "native_unified_runtime_readiness",
            bool(runtime_probe.get("full_autobiographical_recall_ready")),
            actual={
                "status": runtime_probe.get("status"),
                "schema_identity": runtime_probe.get("schema_identity"),
                "memory_search_ready": runtime_probe.get("memory_search_ready"),
                "full_autobiographical_recall_ready": runtime_probe.get(
                    "full_autobiographical_recall_ready"
                ),
                "missing_required_tables": runtime_probe.get("missing_required_tables"),
                "missing_fts_objects": runtime_probe.get("missing_fts_objects"),
                "fts_errors": runtime_probe.get("fts_errors"),
            },
            expected="full_autobiographical_recall_ready=true",
        ))
        ledger = promotion_ledger_validation(path)
        checks.append(_check(
            "l2_l3_verified_from_promotion_ledger", bool(ledger.get("ok")), actual=ledger,
            expected="no automatic commit decisions and every active L3 record backed by promotion decision+ledger",
        ))
        with open_read_only(path) as con:
            tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            invalid_candidates = int(con.execute(
                "SELECT COUNT(*) FROM candidates WHERE confidence<0 OR confidence>1 OR importance<0 OR importance>1"
            ).fetchone()[0]) if "candidates" in tables else 0
            orphan_experiences = int(con.execute(
                "SELECT COUNT(*) FROM experiences e LEFT JOIN candidates c ON c.candidate_id=e.candidate_id WHERE c.candidate_id IS NULL"
            ).fetchone()[0]) if {"experiences", "candidates"}.issubset(tables) else 0
        checks.extend((
            _check("candidate_scores_valid", invalid_candidates == 0, actual=invalid_candidates, expected=0),
            _check("approved_experiences_have_candidates", orphan_experiences == 0, actual=orphan_experiences, expected=0),
        ))
    after = path.stat().st_mtime_ns if path.is_file() else None
    checks.append(_check(
        "validation_did_not_modify_database", before == after,
        actual={"before_mtime_ns": before, "after_mtime_ns": after}, expected="unchanged",
    ))
    blocking_failures = [item for item in checks if item["blocking"] and not item["passed"]]
    warnings = [item for item in checks if not item["blocking"] and not item["passed"]]
    return {
        "ok": not blocking_failures,
        "profile": selected,
        "owner_layer": spec.owner_layer,
        "required_predecessors": list(spec.required_predecessors),
        "gate_kind": spec.gate_kind,
        "database": str(path),
        "canonical_database_name": CANONICAL_DATABASE_NAME,
        "validation": validation,
        "stats": stats,
        "conflicts": conflicts,
        "baseline_reconciliation": reconciliation,
        "test04_acceptance": acceptance,
        "promotion_ledger_validation": ledger,
        "runtime_readiness_probe": runtime_probe,
        "checks": checks,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "read_only": True,
        "system_acceptance": bool(system_acceptance),
        "target_modified": False,
        "automatic_l2": ledger.get("automatic_l2", False) if selected == "final" else False,
        "automatic_l3": ledger.get("automatic_l3", False) if selected == "final" else False,
    }


# Kept for API compatibility; now returns strict aggregate counts and raises on unreadable baselines.
def baseline_counts(roots: Iterable[str | Path]) -> dict[str, int]:
    result = {table: 0 for table in _COMPARE_TABLES}
    for raw in roots:
        for database in _baseline_files(Path(raw).expanduser().resolve()):
            with open_read_only(database) as con:
                tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in _COMPARE_TABLES:
                    if table in tables:
                        result[table] += int(con.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0])
    return result


__all__ = [
    "PROFILE_NAMES",
    "baseline_counts",
    "baseline_record_reconciliation",
    "run_test_profile",
    "semantic_database_fingerprint",
]
