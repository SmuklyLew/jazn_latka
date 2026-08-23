from __future__ import annotations

"""Cryptographically bind source transport archives to canonical memory imports.

The private-memory acceptance flow may attest ZIP transport archives while the
canonical database was built from an extracted ``conversations.json`` member.  A
ZIP SHA-256 and a member SHA-256 are intentionally different values, so provenance
must never infer their relationship from filenames, dates, sizes, or content
similarity.  This module establishes the relationship only when a cryptographic
hash of the archive itself or one of its validated members exactly matches a
completed import record.

The resulting binding is stored in the existing unified-memory ``sources`` and
``links`` tables.  No private source text is copied into the catalog and no memory
promotion is performed.
"""

from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
import argparse
import hashlib
import json
import sqlite3
import zipfile

from latka_jazn.db.runtime_sqlite import connect_runtime_readonly, connect_runtime_writable
from latka_jazn.packaging.zip_resource_limits import validate_zip_resources
from latka_jazn.tools.memory_rebuild_common import canonical_json, now_utc, uid
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("archive_import_provenance")
ARCHIVE_KIND = "chatgpt_export_transport_archive"
ARCHIVE_SOURCE_DATABASE = "private_source_archive"
ARCHIVE_SOURCE_TYPE = "archive_sha256"
IMPORT_TARGET_DATABASE = "memory_jazn.sqlite3"
IMPORT_TARGET_TYPE = "import_source"
RELATION = "cryptographically_contains_import_source"
_CHUNK_SIZE = 8 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member_name(name: str) -> str:
    value = str(name or "").replace("\\", "/")
    parts = PurePosixPath(value).parts
    if not value or value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("unsafe archive member path")
    if len(parts) and parts[0].endswith(":"):
        raise ValueError("absolute archive member path is forbidden")
    return value


def _sha256_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _completed_imports(database: Path) -> dict[str, list[str]]:
    with closing(connect_runtime_readonly(database, timeout_ms=30_000)) as con:
        tables = {
            str(row[0])
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "import_sources" not in tables:
            raise ValueError("canonical database does not contain import_sources")
        rows = con.execute(
            "SELECT import_id,sha256,status FROM import_sources"
        ).fetchall()
    result: dict[str, list[str]] = {}
    for row in rows:
        status = str(row["status"] or "") if "status" in row.keys() else "completed"
        if status and status != "completed":
            continue
        digest = str(row["sha256"] or "").strip().lower()
        import_id = str(row["import_id"] or "").strip()
        if len(digest) == 64 and import_id:
            result.setdefault(digest, []).append(import_id)
    return result


def discover_archive_binding(database: str | Path, archive_path: str | Path) -> dict[str, Any]:
    database_path = Path(database).expanduser().resolve()
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(archive)
    imports = _completed_imports(database_path)
    archive_sha = _sha256_file(archive)
    matches: dict[str, dict[str, Any]] = {}

    for import_id in imports.get(archive_sha, []):
        matches[import_id] = {
            "import_id": import_id,
            "proof_kind": "archive_sha256_exact",
            "proof_sha256": archive_sha,
        }

    if archive.suffix.casefold() == ".zip":
        with zipfile.ZipFile(archive, "r") as source_zip:
            validate_zip_resources(source_zip)
            for info in source_zip.infolist():
                if info.is_dir():
                    continue
                _safe_member_name(info.filename)
                member_sha = _sha256_member(source_zip, info)
                for import_id in imports.get(member_sha, []):
                    matches.setdefault(
                        import_id,
                        {
                            "import_id": import_id,
                            "proof_kind": "archive_member_sha256_exact",
                            "proof_sha256": member_sha,
                        },
                    )

    ordered = sorted(matches.values(), key=lambda item: (str(item["import_id"]), str(item["proof_sha256"])))
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": bool(ordered),
        "archive_sha256": archive_sha,
        "archive_size_bytes": archive.stat().st_size,
        "matched_import_count": len(ordered),
        "matches": ordered,
        "private_path_persisted_in_report": False,
        "private_name_persisted_in_report": False,
        "truth_boundary": (
            "A binding exists only when the SHA-256 of the whole archive or a validated archive member "
            "exactly matches a completed canonical import. Filename/date/size/content-similarity inference is forbidden."
        ),
    }


def _ensure_catalog_tables(con: sqlite3.Connection) -> None:
    required = {"sources", "links", "import_sources"}
    tables = {
        str(row[0])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = sorted(required - tables)
    if missing:
        raise ValueError("canonical database is missing provenance tables: " + ", ".join(missing))


def persist_archive_binding(database: str | Path, binding: dict[str, Any]) -> dict[str, Any]:
    if binding.get("ok") is not True:
        raise ValueError("archive has no cryptographically matched canonical import")
    database_path = Path(database).expanduser().resolve()
    archive_sha = str(binding.get("archive_sha256") or "").strip().lower()
    if len(archive_sha) != 64:
        raise ValueError("archive SHA-256 is invalid")
    matches = [item for item in binding.get("matches") or [] if isinstance(item, dict)]
    if not matches:
        raise ValueError("archive binding contains no imports")

    source_id = uid("source", archive_sha)
    created = now_utc()
    details = {
        "schema_version": SCHEMA_VERSION,
        "relation": RELATION,
        "matched_import_count": len(matches),
        "proofs": [
            {
                "import_id": str(item.get("import_id") or ""),
                "proof_kind": str(item.get("proof_kind") or ""),
                "proof_sha256": str(item.get("proof_sha256") or ""),
            }
            for item in matches
        ],
        "private_path_persisted": False,
        "private_name_persisted": False,
    }

    con = connect_runtime_writable(database_path, timeout_ms=30_000, synchronous="FULL")
    try:
        _ensure_catalog_tables(con)
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            """INSERT INTO sources(source_id,sha256,kind,name,size_bytes,first_seen_at_utc,last_seen_at_utc,details_json)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(sha256) DO UPDATE SET
                 last_seen_at_utc=excluded.last_seen_at_utc,
                 details_json=excluded.details_json""",
            (
                source_id,
                archive_sha,
                ARCHIVE_KIND,
                f"archive:{archive_sha[:16]}",
                int(binding.get("archive_size_bytes") or 0),
                created,
                created,
                canonical_json(details),
            ),
        )
        for item in matches:
            import_id = str(item.get("import_id") or "").strip()
            proof_sha = str(item.get("proof_sha256") or "").strip().lower()
            row = con.execute(
                "SELECT sha256,status FROM import_sources WHERE import_id=?",
                (import_id,),
            ).fetchone()
            if row is None or str(row["status"] or "") not in {"", "completed"}:
                raise ValueError("binding target is not a completed canonical import")
            import_sha = str(row["sha256"] or "").strip().lower()
            if proof_sha not in {archive_sha, import_sha}:
                raise ValueError("binding proof no longer matches target import SHA-256")
            link_id = uid(
                "link",
                ARCHIVE_SOURCE_DATABASE,
                ARCHIVE_SOURCE_TYPE,
                archive_sha,
                IMPORT_TARGET_DATABASE,
                IMPORT_TARGET_TYPE,
                import_id,
                RELATION,
            )
            con.execute(
                """INSERT OR IGNORE INTO links(
                   link_id,source_database,source_type,source_record_id,target_database,target_type,
                   target_record_id,relation,source_sha256,created_at_utc)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    link_id,
                    ARCHIVE_SOURCE_DATABASE,
                    ARCHIVE_SOURCE_TYPE,
                    archive_sha,
                    IMPORT_TARGET_DATABASE,
                    IMPORT_TARGET_TYPE,
                    import_id,
                    RELATION,
                    archive_sha,
                    created,
                ),
            )
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return validate_persisted_archive_binding(database_path, archive_sha)


def validate_persisted_archive_binding(database: str | Path, archive_sha256: str) -> dict[str, Any]:
    database_path = Path(database).expanduser().resolve()
    digest = str(archive_sha256 or "").strip().lower()
    with closing(connect_runtime_readonly(database_path, timeout_ms=30_000)) as con:
        _ensure_catalog_tables(con)
        source = con.execute(
            "SELECT source_id,kind FROM sources WHERE sha256=?",
            (digest,),
        ).fetchone()
        links = con.execute(
            """SELECT l.target_record_id,l.source_sha256,i.sha256 AS import_sha256,i.status
               FROM links AS l
               LEFT JOIN import_sources AS i ON i.import_id=l.target_record_id
               WHERE l.source_database=? AND l.source_type=? AND l.source_record_id=?
                 AND l.target_database=? AND l.target_type=? AND l.relation=?""",
            (
                ARCHIVE_SOURCE_DATABASE,
                ARCHIVE_SOURCE_TYPE,
                digest,
                IMPORT_TARGET_DATABASE,
                IMPORT_TARGET_TYPE,
                RELATION,
            ),
        ).fetchall()
    valid_links = [
        row for row in links
        if str(row["source_sha256"] or "").lower() == digest
        and row["import_sha256"]
        and str(row["status"] or "") in {"", "completed"}
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": source is not None and str(source["kind"] or "") == ARCHIVE_KIND and bool(valid_links),
        "archive_sha256": digest,
        "binding_count": len(valid_links),
        "bound_import_ids": sorted(str(row["target_record_id"]) for row in valid_links),
        "private_path_persisted_in_report": False,
        "private_name_persisted_in_report": False,
    }


def bind_archives(database: str | Path, archives: Iterable[str | Path], *, write: bool) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    for archive in archives:
        discovered = discover_archive_binding(database, archive)
        if write and discovered.get("ok") is True:
            persisted = persist_archive_binding(database, discovered)
        else:
            persisted = {
                "ok": False,
                "binding_count": 0,
                "status": "dry_run" if discovered.get("ok") else "unmatched",
            }
        reports.append(
            {
                "archive_sha256": discovered.get("archive_sha256"),
                "matched_import_count": discovered.get("matched_import_count", 0),
                "cryptographic_match_ok": bool(discovered.get("ok")),
                "persisted_binding_ok": bool(persisted.get("ok")) if write else None,
                "persisted_binding_count": persisted.get("binding_count", 0),
            }
        )
    ok = bool(reports) and all(
        item["cryptographic_match_ok"] and (not write or item["persisted_binding_ok"])
        for item in reports
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "write_performed": bool(write),
        "archive_count": len(reports),
        "bound_archive_count": sum(1 for item in reports if item.get("persisted_binding_ok")),
        "archives": reports,
        "private_paths_persisted_in_report": False,
        "private_names_persisted_in_report": False,
    }


def _load_manifest_archives(path: Path) -> list[Path]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        raise ValueError("source manifest must contain a sources list")
    result: list[Path] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("path") or "").strip()
        if raw:
            result.append(Path(raw).expanduser())
    if not result:
        raise ValueError("source manifest contains no archive paths")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="archive_import_provenance",
        description="Bind source archive SHA-256 values to canonical unified-memory imports.",
        allow_abbrev=False,
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = bind_archives(
        args.database,
        _load_manifest_archives(args.source_manifest),
        write=bool(args.write),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"archive provenance: ok={report['ok']} bound={report['bound_archive_count']}/{report['archive_count']}")
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
