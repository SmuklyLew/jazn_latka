from __future__ import annotations

"""Read-only checks of source file integrity and supported formats.

Checks are NOT rebuild steps. No source file, live memory database, canonical
memory, L1/L2/L3 candidate or activation state is written by this module.
"""

from collections import Counter
from pathlib import Path
from typing import Any, Iterable
import codecs
import json
import os
import zipfile

from .report_sanitizer import write_report_pair
from latka_jazn.tools.chat_export_reader import ChatExportReader
from .source_inventory import inspect_source, inspect_zip


CHECK_SCHEMA = "jazn_memory_studio_file_checks/v1"
_TEXT_EXTENSIONS = frozenset({".txt", ".md", ".html", ".htm"})
_ZIP_DOCUMENTS = frozenset({".odt", ".ods", ".odp"})


def _check_utf8(path: Path) -> dict[str, Any]:
    """Decode incrementally with a fixed memory cap; do not retain private text."""
    decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
    bytes_read = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            decoder.decode(chunk)
            bytes_read += len(chunk)
        decoder.decode(b"", final=True)
    return {"encoding": "utf-8", "byte_count": bytes_read, "ok": True}


def _check_jsonl(path: Path) -> dict[str, Any]:
    """Validate every JSONL record, not only the first lines in source sniffing."""
    records = 0
    with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except (json.JSONDecodeError, ValueError) as exc:
                # Error strings may include private material: expose type and line only.
                raise ValueError(f"invalid JSONL at line {line_no} ({type(exc).__name__})") from None
            records += 1
    return {"record_count": records, "ok": True}


def _check_json(path: Path, *, canonical_chat: bool, legacy_recovered: bool) -> dict[str, Any]:
    """Validate entire JSON, streaming canonical ChatGPT arrays by conversation.

    Legacy repair must be reviewed separately; tests never rewrite or silently
    accept a syntax-repaired source as a lossless original.
    """
    if legacy_recovered:
        return {"ok": True, "status": "legacy_recovery_requires_review"}
    if canonical_chat:
        with ChatExportReader(path, verify_crc=False) as reader:
            count = sum(1 for _ in reader.iter_raw_conversations())
        return {"ok": True, "status": "full_stream_parse", "conversation_count": count}

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate_json_object_key")
            value[key] = item
        return value

    # Do not materialize unbounded non-chat JSON files. A format-specific
    # streaming adapter is required for larger metadata sources.
    if path.stat().st_size > 64 * 1024 * 1024:
        return {"ok": True, "status": "large_generic_json_requires_adapter"}
    with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
        json.load(stream, object_pairs_hook=unique_pairs)
    return {"ok": True, "status": "full_json_parse"}


def _check_office_package(path: Path) -> dict[str, Any]:
    meta = inspect_zip(path, verify_crc=True)
    blocking_keys = ("unsafe_members", "symlink_members", "duplicate_members", "case_collisions")
    reasons = [key for key in blocking_keys if meta.get(key)]
    if meta.get("crc_error_member"):
        reasons.append("crc_error")
    try:
        with zipfile.ZipFile(path) as archive:
            mime = archive.read("mimetype").decode("ascii", errors="strict")
    except (KeyError, UnicodeError, zipfile.BadZipFile):
        mime = ""
        reasons.append("odf_mimetype_missing")
    expected = {
        ".odt": "application/vnd.oasis.opendocument.text",
        ".ods": "application/vnd.oasis.opendocument.spreadsheet",
        ".odp": "application/vnd.oasis.opendocument.presentation",
    }[path.suffix.lower()]
    if mime != expected:
        reasons.append("odf_mimetype_mismatch")
    return {
        "ok": not reasons,
        "odf_mimetype_valid": mime == expected,
        "crc_checked": bool(meta.get("crc_checked")),
        "member_count": int(meta.get("member_count") or 0),
        "blocking_codes": reasons,
    }


def check_memory_source_files(
    sources: Iterable[str | Path],
    *,
    report_dir: str | Path | None = None,
    max_files: int = 10000,
) -> dict[str, Any]:
    """Inventory and check formats without importing; fail closed on missing files."""
    if max_files < 1:
        raise ValueError("max_files must be positive")
    checked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in sources:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            paths = sorted(
                (candidate for candidate in path.rglob("*") if candidate.is_file()),
                key=lambda candidate: candidate.as_posix().casefold(),
            )
        else:
            paths = [path]
        for source in paths:
            key = os.path.normcase(str(source))
            if key in seen:
                continue
            seen.add(key)
            if len(checked) >= max_files:
                raise ValueError("file_check_limit_exceeded")
            try:
                inspected = inspect_source(source, calculate_sha256=True, verify_zip_crc=True)
                details = inspected.to_dict()
                blockers = [warning for warning in inspected.warnings if warning.startswith("blocking:")]
                format_check: dict[str, Any] = {"status": "not_applicable"}
                suffix = source.suffix.lower()
                if inspected.exists and inspected.is_file and not blockers:
                    if suffix == ".json":
                        format_check = _check_json(
                            source,
                            canonical_chat=inspected.role == "chatgpt_export",
                            legacy_recovered="legacy_json_recovered" in inspected.warnings,
                        )
                    elif suffix in _TEXT_EXTENSIONS:
                        format_check = _check_utf8(source)
                    elif suffix in {".jsonl", ".ndjson"}:
                        format_check = _check_jsonl(source)
                    elif suffix in _ZIP_DOCUMENTS:
                        format_check = _check_office_package(source)
                        if not format_check["ok"]:
                            blockers.extend(format_check["blocking_codes"])
                needs_review = (
                    any("legacy_json_recovered" in warning for warning in inspected.warnings)
                    or inspected.role == "unknown"
                    or inspected.pipeline in {"catalog_only", "excluded"}
                    or format_check.get("status") in {
                        "legacy_recovery_requires_review", "large_generic_json_requires_adapter"
                    }
                )
                if blockers:
                    status = "FAILED"
                elif needs_review:
                    status = "REVIEW"
                else:
                    status = "PASSED"
                checked.append({
                    "path": str(source),
                    "source_sha256": inspected.sha256,
                    "size_bytes": inspected.size_bytes,
                    "format": suffix,
                    "role": inspected.role,
                    "pipeline": inspected.pipeline,
                    "status": status,
                    "blocking_codes": blockers,
                    "warning_codes": inspected.warnings,
                    "format_check": format_check,
                })
            except (OSError, ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError) as exc:
                checked.append({
                    "path": str(source),
                    "format": source.suffix.lower(),
                    "status": "FAILED",
                    "blocking_codes": [f"format_validation_{type(exc).__name__}"],
                    "error_type": type(exc).__name__,
                })
    if not checked:
        raise ValueError("no_source_files_selected")
    counts = dict(Counter(row["status"] for row in checked))
    report: dict[str, Any] = {
        "schema_version": CHECK_SCHEMA,
        "ok": counts.get("FAILED", 0) == 0,
        "status": "FAILED" if counts.get("FAILED") else ("REVIEW" if counts.get("REVIEW") else "PASSED"),
        "file_count": len(checked),
        "total_size_bytes": sum(int(x.get("size_bytes") or 0) for x in checked),
        "counts": counts,
        "files": checked,
        "truth_boundary": "Source file checks do not import, rebuild, approve memory or activate the runtime.",
    }
    if report_dir is not None:
        report["report_paths"] = write_report_pair(report_dir, "file-checks", report)
    return report


__all__ = ["CHECK_SCHEMA", "check_memory_source_files"]
