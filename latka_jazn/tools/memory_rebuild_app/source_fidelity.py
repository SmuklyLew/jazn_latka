from __future__ import annotations

"""Test00: byte-faithful source mirror plus independent structural census.

The source mirror is intentionally *not* a memory database. It stores exact
input bytes in bounded chunks plus descriptive parse metadata. No row from this
database can become L1/L2/L3 and no recall API reads it directly.
"""

from collections import Counter
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable
import json
import os
import sqlite3
import uuid
import zipfile

from latka_jazn.tools.chat_export_reader import (
    ChatExportReader,
    build_conversation_graph,
    probe_json_source_kind,
    sha256_file,
)

from .html_import import read_html_conversations
from .test_spec import TestOutcome


SOURCE_MIRROR_SCHEMA = "jazn_memory_rebuild_source_mirror/v2"
TEST00_REPORT_SCHEMA = "jazn_memory_rebuild_test00/v1"
CHUNK_SIZE = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SourceFidelityResult:
    source_id: str
    source_path: str
    source_name: str
    source_sha256: str
    size_bytes: int
    source_kind: str
    parse_mode: str
    outcome: str
    raw_roundtrip_sha256: str
    raw_chunk_count: int
    conversation_count: int
    node_count: int
    message_count: int
    branch_point_count: int
    role_counts: dict[str, int]
    content_type_counts: dict[str, int]
    zip_member_count: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def default_test00_root(tool_root: str | Path) -> Path:
    return Path(tool_root).expanduser().resolve() / "memory" / "rebuild_tests" / "test_00"


def _connect(database: Path) -> sqlite3.Connection:
    con = sqlite3.connect(database, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    return con


def _initialize(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_mirror_meta(
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_mirror_sources(
          source_pk INTEGER PRIMARY KEY AUTOINCREMENT,
          source_id TEXT NOT NULL UNIQUE,
          source_name TEXT NOT NULL,
          source_path TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_sha256 TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          raw_chunk_count INTEGER NOT NULL DEFAULT 0,
          raw_roundtrip_sha256 TEXT,
          parse_mode TEXT NOT NULL DEFAULT 'unparsed',
          fidelity_status TEXT NOT NULL DEFAULT 'NOT RUN',
          conversation_count INTEGER NOT NULL DEFAULT 0,
          node_count INTEGER NOT NULL DEFAULT 0,
          message_count INTEGER NOT NULL DEFAULT 0,
          branch_point_count INTEGER NOT NULL DEFAULT 0,
          details_json TEXT NOT NULL DEFAULT '{}',
          created_at_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_mirror_chunks(
          source_id TEXT NOT NULL,
          chunk_index INTEGER NOT NULL,
          chunk_sha256 TEXT NOT NULL,
          chunk_size INTEGER NOT NULL,
          data BLOB NOT NULL,
          PRIMARY KEY(source_id,chunk_index),
          FOREIGN KEY(source_id) REFERENCES source_mirror_sources(source_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS source_mirror_roles(
          source_id TEXT NOT NULL,
          role TEXT NOT NULL,
          observed_count INTEGER NOT NULL,
          PRIMARY KEY(source_id,role),
          FOREIGN KEY(source_id) REFERENCES source_mirror_sources(source_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS source_mirror_content_types(
          source_id TEXT NOT NULL,
          content_type TEXT NOT NULL,
          observed_count INTEGER NOT NULL,
          PRIMARY KEY(source_id,content_type),
          FOREIGN KEY(source_id) REFERENCES source_mirror_sources(source_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS source_mirror_zip_members(
          source_id TEXT NOT NULL,
          member_name TEXT NOT NULL,
          member_sha256 TEXT NOT NULL,
          crc32 INTEGER NOT NULL,
          compressed_size INTEGER NOT NULL,
          uncompressed_size INTEGER NOT NULL,
          PRIMARY KEY(source_id,member_name),
          FOREIGN KEY(source_id) REFERENCES source_mirror_sources(source_id) ON DELETE CASCADE
        );
        """
    )
    con.execute(
        "INSERT OR REPLACE INTO source_mirror_meta(key,value) VALUES('schema_version',?)",
        (SOURCE_MIRROR_SCHEMA,),
    )
    con.execute(
        "INSERT OR REPLACE INTO source_mirror_meta(key,value) VALUES('chunk_size_bytes',?)",
        (str(CHUNK_SIZE),),
    )
    con.execute(
        "INSERT OR REPLACE INTO source_mirror_meta(key,value) VALUES('truth_boundary',?)",
        (
            "Source mirror proves byte/parse fidelity only; it is not L1/L2/L3, recall, truth, or activation.",
        ),
    )
    con.commit()


def _stream_raw_into_chunks(
    con: sqlite3.Connection,
    source: Path,
    source_id: str,
    source_kind: str,
) -> tuple[str, str, int]:
    """Mirror a file with bounded BLOB rows and verify whole-file round-trip SHA.

    A single SQLite BLOB has a configurable maximum length (commonly 1 GB), while
    real ChatGPT exports can be larger. Test00 therefore stores fixed-size chunks
    and reconstructs the whole-file digest from ordered chunk rows.
    """

    size = source.stat().st_size
    con.execute(
        """INSERT INTO source_mirror_sources(
             source_id,source_name,source_path,source_kind,source_sha256,size_bytes,created_at_utc
           ) VALUES(?,?,?,?,?,?,?)""",
        (source_id, source.name, str(source), source_kind, "pending", size, _utc_now()),
    )
    digest = sha256()
    chunk_count = 0
    total = 0
    with source.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            con.execute(
                """INSERT INTO source_mirror_chunks(
                     source_id,chunk_index,chunk_sha256,chunk_size,data
                   ) VALUES(?,?,?,?,?)""",
                (source_id, chunk_count, sha256(chunk).hexdigest(), len(chunk), sqlite3.Binary(chunk)),
            )
            chunk_count += 1
    if total != size:
        raise RuntimeError(f"source size changed while mirroring: expected={size}, observed={total}")
    source_hash = digest.hexdigest()
    con.execute(
        "UPDATE source_mirror_sources SET source_sha256=?,raw_chunk_count=? WHERE source_id=?",
        (source_hash, chunk_count, source_id),
    )
    con.commit()

    roundtrip = sha256()
    reconstructed_size = 0
    rows = con.execute(
        "SELECT chunk_index,chunk_sha256,chunk_size,data FROM source_mirror_chunks WHERE source_id=? ORDER BY chunk_index",
        (source_id,),
    )
    expected_index = 0
    for row in rows:
        index = int(row[0])
        if index != expected_index:
            raise RuntimeError(f"source mirror chunk sequence gap: expected={expected_index}, observed={index}")
        data = bytes(row[3])
        declared_size = int(row[2])
        if len(data) != declared_size:
            raise RuntimeError(f"source mirror chunk size mismatch at index {index}")
        if sha256(data).hexdigest() != str(row[1]):
            raise RuntimeError(f"source mirror chunk SHA mismatch at index {index}")
        roundtrip.update(data)
        reconstructed_size += len(data)
        expected_index += 1
    if reconstructed_size != size or expected_index != chunk_count:
        raise RuntimeError("source mirror reconstruction count/size mismatch")
    roundtrip_hash = roundtrip.hexdigest()
    con.execute(
        "UPDATE source_mirror_sources SET raw_roundtrip_sha256=? WHERE source_id=?",
        (roundtrip_hash, source_id),
    )
    con.commit()
    return source_hash, roundtrip_hash, chunk_count


def _raw_census(conversation: dict[str, Any]) -> tuple[int, int, int, Counter[str], Counter[str]]:
    mapping_value = conversation.get("mapping")
    mapping = mapping_value if isinstance(mapping_value, dict) else {}
    messages = 0
    branches = 0
    roles: Counter[str] = Counter()
    content_types: Counter[str] = Counter()
    for raw_node in mapping.values():
        if not isinstance(raw_node, dict):
            continue
        if len(raw_node.get("children") or []) > 1:
            branches += 1
        message = raw_node.get("message")
        if not isinstance(message, dict) or not message:
            continue
        messages += 1
        author = message.get("author")
        role = str(author.get("role")) if isinstance(author, dict) and author.get("role") is not None else "<none>"
        content = message.get("content")
        content_type = (
            str(content.get("content_type"))
            if isinstance(content, dict) and content.get("content_type") is not None
            else "unknown"
        )
        roles[role] += 1
        content_types[content_type] += 1
    return len(mapping), messages, branches, roles, content_types


def _iter_and_compare(conversations: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    counts: dict[str, Any] = {
        "conversations": 0,
        "nodes": 0,
        "messages": 0,
        "branch_points": 0,
        "roles": Counter(),
        "content_types": Counter(),
    }
    errors: list[str] = []
    for raw in conversations:
        raw_nodes, raw_messages, raw_branches, raw_roles, raw_types = _raw_census(raw)
        graph = build_conversation_graph(raw)
        parsed_roles = Counter(
            (node.role if node.role is not None else "<none>")
            for node in graph.nodes
            if node.message_id is not None
        )
        parsed_types = Counter(
            node.content_type or "unknown"
            for node in graph.nodes
            if node.message_id is not None
        )
        if graph.node_count != raw_nodes:
            errors.append(f"node_count_mismatch:{graph.conversation_id}:{raw_nodes}!={graph.node_count}")
        if graph.message_count != raw_messages:
            errors.append(f"message_count_mismatch:{graph.conversation_id}:{raw_messages}!={graph.message_count}")
        if len(graph.branch_points) != raw_branches:
            errors.append(f"branch_count_mismatch:{graph.conversation_id}:{raw_branches}!={len(graph.branch_points)}")
        if parsed_roles != raw_roles:
            errors.append(f"role_inventory_mismatch:{graph.conversation_id}")
        if parsed_types != raw_types:
            errors.append(f"content_type_inventory_mismatch:{graph.conversation_id}")
        counts["conversations"] = int(counts["conversations"]) + 1
        counts["nodes"] = int(counts["nodes"]) + raw_nodes
        counts["messages"] = int(counts["messages"]) + raw_messages
        counts["branch_points"] = int(counts["branch_points"]) + raw_branches
        roles_value = counts["roles"]
        types_value = counts["content_types"]
        if isinstance(roles_value, Counter):
            roles_value.update(raw_roles)
        if isinstance(types_value, Counter):
            types_value.update(raw_types)
    return counts, errors


def _read_generic_json(path: Path) -> dict[str, Any]:
    """Read a non-conversation JSON source fully without persisting private values in reports."""
    with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
        value = json.load(stream)
    if isinstance(value, list):
        sample_keys = {
            str(key)
            for row in value[:32]
            if isinstance(row, dict)
            for key in row
        }
        return {
            "json_top_level": "array",
            "record_count": len(value),
            "sample_key_count": len(sample_keys),
        }
    if isinstance(value, dict):
        return {
            "json_top_level": "object",
            "record_count": 1,
            "top_level_key_count": len(value),
        }
    return {"json_top_level": type(value).__name__, "record_count": 1}


def _hash_zip_members(path: Path, con: sqlite3.Connection, source_id: str) -> int:
    count = 0
    with zipfile.ZipFile(path, "r") as archive:
        # ChatExportReader has already enforced path/resource/collision rules and CRC.
        for info in archive.infolist():
            if info.is_dir():
                continue
            digest = sha256()
            with archive.open(info, "r") as stream:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
            con.execute(
                """INSERT INTO source_mirror_zip_members(
                     source_id,member_name,member_sha256,crc32,compressed_size,uncompressed_size
                   ) VALUES(?,?,?,?,?,?)""",
                (source_id, info.filename, digest.hexdigest(), int(info.CRC), int(info.compress_size), int(info.file_size)),
            )
            count += 1
    con.commit()
    return count


def _parse_source(
    path: Path,
    con: sqlite3.Connection,
    source_id: str,
    *, allow_opaque: bool = False,
) -> tuple[str, str, dict[str, Any], list[str], list[str], int]:
    suffix = path.suffix.casefold()
    warnings: list[str] = []
    errors: list[str] = []
    zip_members = 0
    details: dict[str, Any] = {}
    outcome = TestOutcome.PASSED.value
    parse_mode = "generic"

    if suffix == ".zip":
        with ChatExportReader(path, verify_crc=True) as reader:
            zip_members = _hash_zip_members(path, con, source_id)
            details["crc_checked"] = bool(reader.info.crc_checked)
            details["crc_ok"] = bool(reader.info.crc_ok)
            details["canonical_conversation_members"] = len(reader.info.conversation_members)
            details["shared_conversation_members"] = len(reader.info.shared_conversations_members)
            if reader.info.conversation_members:
                parse_mode = "canonical_json_in_zip"
                counts, compare_errors = _iter_and_compare(reader.iter_raw_conversations())
                errors.extend(compare_errors)
                details.update(counts)
            elif reader.info.html_member:
                records, member, html_mode, html_warnings = read_html_conversations(path)
                parse_mode = f"html_in_zip:{html_mode}"
                details["html_member"] = member
                warnings.extend(html_warnings)
                counts, compare_errors = _iter_and_compare(records)
                errors.extend(compare_errors)
                details.update(counts)
                if html_mode in {"rendered_html_fallback", "rendered_html_lossy"}:
                    outcome = TestOutcome.LOSSY.value
            else:
                outcome = TestOutcome.BLOCKED.value
                errors.append("zip_has_no_supported_conversation_source")
        return parse_mode, outcome, details, warnings, errors, zip_members

    if suffix in {".html", ".htm"}:
        records, member, html_mode, html_warnings = read_html_conversations(path)
        parse_mode = html_mode
        details["html_member"] = member
        warnings.extend(html_warnings)
        counts, compare_errors = _iter_and_compare(records)
        errors.extend(compare_errors)
        details.update(counts)
        if html_mode in {"rendered_html_fallback", "rendered_html_lossy"}:
            outcome = TestOutcome.LOSSY.value
        return parse_mode, outcome, details, warnings, errors, 0

    if suffix == ".json":
        source_kind = probe_json_source_kind(path)
        details["json_source_kind"] = source_kind
        if source_kind == "conversation":
            parse_mode = "canonical_json"
            with ChatExportReader(path, verify_crc=False) as reader:
                counts, compare_errors = _iter_and_compare(reader.iter_raw_conversations())
            errors.extend(compare_errors)
            details.update(counts)
        else:
            parse_mode = f"sidecar_json:{source_kind}"
            details.update(_read_generic_json(path))
        return parse_mode, outcome, details, warnings, errors, 0

    if allow_opaque:
        return "opaque_source_evidence", TestOutcome.PASSED.value, {"parsed": False}, warnings, errors, 0

    return "unsupported", TestOutcome.BLOCKED.value, details, warnings, ["unsupported_source_type"], 0


def _persist_census(con: sqlite3.Connection, source_id: str, details: dict[str, Any]) -> None:
    roles = details.get("roles")
    if isinstance(roles, Counter):
        for role, count in sorted(roles.items()):
            con.execute(
                "INSERT INTO source_mirror_roles(source_id,role,observed_count) VALUES(?,?,?)",
                (source_id, str(role), int(count)),
            )
    content_types = details.get("content_types")
    if isinstance(content_types, Counter):
        for content_type, count in sorted(content_types.items()):
            con.execute(
                "INSERT INTO source_mirror_content_types(source_id,content_type,observed_count) VALUES(?,?,?)",
                (source_id, str(content_type), int(count)),
            )


def _json_safe_details(details: dict[str, Any]) -> dict[str, Any]:
    result = dict(details)
    for key in ("roles", "content_types"):
        value = result.get(key)
        if isinstance(value, Counter):
            result[key] = dict(sorted((str(item), int(count)) for item, count in value.items()))
    return result


def _inspect_one(path: Path, con: sqlite3.Connection, *, allow_opaque: bool = False) -> SourceFidelityResult:
    source_id = f"src-{uuid.uuid4().hex}"
    suffix = path.suffix.casefold()
    source_kind = {".json": "json", ".html": "html", ".htm": "html", ".zip": "zip"}.get(suffix, "unknown")
    source_hash, roundtrip_hash, chunk_count = _stream_raw_into_chunks(con, path, source_id, source_kind)
    warnings: list[str] = []
    errors: list[str] = []
    details: dict[str, Any] = {}
    zip_member_count = 0
    try:
        parse_mode, outcome, details, warnings, errors, zip_member_count = _parse_source(
            path, con, source_id, allow_opaque=allow_opaque,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        parse_mode = "parse_failed"
        outcome = TestOutcome.FAILED.value
        errors.append(f"{type(exc).__name__}:{exc}")
    if roundtrip_hash != source_hash:
        outcome = TestOutcome.FAILED.value
        errors.append("raw_roundtrip_sha256_mismatch")
    if errors and outcome not in {TestOutcome.BLOCKED.value, TestOutcome.LOSSY.value}:
        outcome = TestOutcome.FAILED.value

    _persist_census(con, source_id, details)
    safe_details = _json_safe_details(details)
    roles_value = safe_details.get("roles")
    roles = roles_value if isinstance(roles_value, dict) else {}
    content_types_value = safe_details.get("content_types")
    content_types = content_types_value if isinstance(content_types_value, dict) else {}
    con.execute(
        """UPDATE source_mirror_sources SET
             raw_roundtrip_sha256=?,parse_mode=?,fidelity_status=?,conversation_count=?,node_count=?,
             message_count=?,branch_point_count=?,details_json=? WHERE source_id=?""",
        (
            roundtrip_hash,
            parse_mode,
            outcome,
            int(safe_details.get("conversations") or 0),
            int(safe_details.get("nodes") or 0),
            int(safe_details.get("messages") or 0),
            int(safe_details.get("branch_points") or 0),
            json.dumps(
                {"warnings": warnings, "errors": errors, **safe_details},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            source_id,
        ),
    )
    con.commit()
    return SourceFidelityResult(
        source_id=source_id,
        source_path=str(path),
        source_name=path.name,
        source_sha256=source_hash,
        size_bytes=path.stat().st_size,
        source_kind=source_kind,
        parse_mode=parse_mode,
        outcome=outcome,
        raw_roundtrip_sha256=roundtrip_hash,
        raw_chunk_count=chunk_count,
        conversation_count=int(safe_details.get("conversations") or 0),
        node_count=int(safe_details.get("nodes") or 0),
        message_count=int(safe_details.get("messages") or 0),
        branch_point_count=int(safe_details.get("branch_points") or 0),
        role_counts={str(key): int(value) for key, value in roles.items()},
        content_type_counts={str(key): int(value) for key, value in content_types.items()},
        zip_member_count=zip_member_count,
        warnings=tuple(warnings),
        errors=tuple(errors),
    )


def _aggregate_outcome(results: list[SourceFidelityResult]) -> str:
    values = {item.outcome for item in results}
    if TestOutcome.FAILED.value in values:
        return TestOutcome.FAILED.value
    if TestOutcome.BLOCKED.value in values:
        return TestOutcome.BLOCKED.value
    if TestOutcome.LOSSY.value in values:
        return TestOutcome.LOSSY.value
    return TestOutcome.PASSED.value if results else TestOutcome.BLOCKED.value


def _sanitized_result(item: SourceFidelityResult) -> dict[str, Any]:
    return {
        "source_id": item.source_id,
        "source_name_sha256": _sha_text(item.source_name),
        "source_path_sha256": _sha_text(item.source_path),
        "source_sha256": item.source_sha256,
        "size_bytes": item.size_bytes,
        "source_kind": item.source_kind,
        "parse_mode": item.parse_mode,
        "outcome": item.outcome,
        "raw_roundtrip_sha256": item.raw_roundtrip_sha256,
        "raw_chunk_count": item.raw_chunk_count,
        "conversation_count": item.conversation_count,
        "node_count": item.node_count,
        "message_count": item.message_count,
        "branch_point_count": item.branch_point_count,
        "role_counts": dict(item.role_counts),
        "content_type_counts": dict(item.content_type_counts),
        "zip_member_count": item.zip_member_count,
        "warning_count": len(item.warnings),
        "error_count": len(item.errors),
        "private_content_persisted_in_report": False,
    }


def run_test00_source_fidelity(
    sources: Iterable[str | Path],
    *,
    output_root: str | Path,
    run_id: str | None = None,
    opaque_evidence: Iterable[str | Path] = (),
) -> dict[str, Any]:
    source_paths: list[Path] = []
    seen: set[str] = set()
    for item in sources:
        path = Path(item).expanduser().resolve()
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        source_paths.append(path)
    if not source_paths:
        raise ValueError("Test00 requires at least one source")
    for path in source_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    opaque_keys = {
        os.path.normcase(str(Path(item).expanduser().resolve()))
        for item in opaque_evidence
    }

    root = Path(output_root).expanduser().resolve()
    resolved_run_id = run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    run_root = root / resolved_run_id
    run_root.mkdir(parents=True, exist_ok=False)
    database = run_root / "source_mirror.sqlite3"
    results: list[SourceFidelityResult] = []
    with closing(_connect(database)) as con:
        _initialize(con)
        for path in source_paths:
            results.append(_inspect_one(
                path, con,
                allow_opaque=os.path.normcase(str(path)) in opaque_keys,
            ))
        integrity = [str(row[0]) for row in con.execute("PRAGMA integrity_check")]
        foreign_keys = [tuple(row) for row in con.execute("PRAGMA foreign_key_check")]
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.commit()

    outcome = _aggregate_outcome(results)
    if integrity != ["ok"] or foreign_keys:
        outcome = TestOutcome.FAILED.value
    private_report = {
        "schema_version": TEST00_REPORT_SCHEMA,
        "source_mirror_schema": SOURCE_MIRROR_SCHEMA,
        "run_id": resolved_run_id,
        "outcome": outcome,
        "database": str(database),
        "database_sha256": sha256_file(database),
        "source_count": len(results),
        "integrity": integrity,
        "foreign_key_error_count": len(foreign_keys),
        "sources": [item.to_dict() for item in results],
        "truth_boundary": (
            "Test00 proves source read/storage fidelity only. It does not establish autobiographical truth, "
            "memory eligibility, recall quality, L2/L3 promotion, or active Jaźń."
        ),
        "automatic_l2": False,
        "automatic_l3": False,
        "automatic_activation": False,
    }
    sanitized_report = {
        **{key: value for key, value in private_report.items() if key not in {"database", "sources"}},
        "database_path_persisted": False,
        "sources": [_sanitized_result(item) for item in results],
    }
    private_path = run_root / "summary.private.json"
    sanitized_path = run_root / "summary.sanitized.json"
    private_path.write_text(json.dumps(private_report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    sanitized_path.write_text(json.dumps(sanitized_report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {
        "ok": outcome == TestOutcome.PASSED.value,
        "outcome": outcome,
        "run_id": resolved_run_id,
        "run_root": str(run_root),
        "database": str(database),
        "database_sha256": private_report["database_sha256"],
        "private_report": str(private_path),
        "sanitized_report": str(sanitized_path),
        "source_count": len(results),
        "results": [item.to_dict() for item in results],
        "automatic_l2": False,
        "automatic_l3": False,
        "automatic_activation": False,
    }


__all__ = [
    "CHUNK_SIZE",
    "SOURCE_MIRROR_SCHEMA",
    "TEST00_REPORT_SCHEMA",
    "SourceFidelityResult",
    "default_test00_root",
    "run_test00_source_fidelity",
]
