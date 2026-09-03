from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
import hashlib
import json
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import zipfile

from latka_jazn.memory.session_continuity import SessionContinuityManager
from latka_jazn.core.version_source import read_runtime_version_from_version_py
from latka_jazn.packaging.zip_resource_limits import ZipResourceLimitError, validate_zip_resources
from latka_jazn.tools.safe_paths import (
    UnsafeRelativePathError,
    resolve_safe_destination,
    resolve_safe_source,
    validate_safe_relative_path,
)
from latka_jazn.version import PACKAGE_VERSION

SYSTEM_EXCLUDE_PREFIXES = (
    "memory/",
    "workspace_runtime/",
    "exports/",
    "backups/",
)
NLP_INCLUDE_PREFIXES = (
    "latka_jazn/nlp/",
    "latka_jazn/resources/",
)
NLP_INCLUDE_EXACT: set[str] = set()

GITHUB_SAFE_EXCLUDE_PREFIXES = (
    "memory/",
    "workspace_runtime/",
    "exports/",
    "backups/",
)
# Source-safe means safe by provenance and content, not merely by directory.
GITHUB_SAFE_PRIVATE_EXACT = {
    "latka_jazn/core/canon/local_private_canon_extension.py",
}
_PRIVATE_MARKER_PARTS = (
    ("local_private", "do_not_commit_without_review"),
    ("generated_from", "private_memory"),
    ("raw_conversation", "embedded_source"),
)
COMMON_EXCLUDE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".archives",
}
COMMON_EXCLUDE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".tmp",
    ".bak",
    ".zip",
    ".sqlite3-wal",
    ".sqlite3-shm",
    "-wal",
    "-shm",
)
FORBIDDEN_PACKAGE_PREFIXES = (
    ".archives/",
    "workspace_runtime/",
    "backups/",
    "requests/",
    "responses/",
    "processed/",
    "status/",
    "logs/",
    "log/",
    ".pytest_cache/",
)
FORBIDDEN_PACKAGE_EXACT = {
    ".archives",
    "workspace_runtime",
    "workspace_runtime/JAZN_ACTIVE_RUNTIME.json",
    "ACTIVE_RUNTIME_CACHE_CONTRACT.json",
    "BOOTSTRAP_JAZN_CURRENT.json",
    "RUNTIME_STATE.json",
    "runtime_session_state.json",
    ".pytest_cache",
}
FORBIDDEN_PACKAGE_GLOBS = (
    "workspace_runtime/pytest_*",
    "runtime-preview-*.json",
    "*.sqlite3-wal",
    "*.sqlite3-shm",
    "*/codex_session_bridge/requests/*",
    "*/codex_session_bridge/responses/*",
    "*/codex_session_bridge/processed/*",
    "*/codex_session_bridge/status/*",
    "*/codex_session_bridge/logs/*",
    "*/codex_session_bridge/log/*",
)


class PackagePlanValidationError(ValueError):
    pass


@dataclass(slots=True)
class PackageExportReport:
    mode: str
    output_zip: str
    created_at_utc: str
    file_count: int
    total_uncompressed_bytes: int
    zip_size_bytes: int
    sha256: str
    includes_memory: bool
    includes_system: bool
    package_manifest_path: str
    packing_audit_path: str
    crc_ok: bool
    extract_smoke_ok: bool
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


SYSTEM_INTEGRITY_MANIFEST_NAME = "PACKAGE_INTEGRITY_MANIFEST.json"


def _system_integrity_contract(root: Path) -> tuple[dict, dict[str, dict]]:
    manifest_path = root / SYSTEM_INTEGRITY_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagePlanValidationError(f"System integrity manifest is unavailable or invalid: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise PackagePlanValidationError("System integrity manifest does not contain a files list")
    entries: dict[str, dict] = {}
    for raw_entry in payload["files"]:
        if not isinstance(raw_entry, dict):
            raise PackagePlanValidationError("System integrity manifest contains a non-object entry")
        try:
            rel = validate_safe_relative_path(str(raw_entry.get("path") or ""))
        except UnsafeRelativePathError as exc:
            raise PackagePlanValidationError(f"Unsafe path in system integrity manifest: {raw_entry.get('path')!r}") from exc
        if rel == SYSTEM_INTEGRITY_MANIFEST_NAME or rel in entries:
            raise PackagePlanValidationError(f"Duplicate or self-referential system integrity path: {rel}")
        if forbidden_package_reason(rel) or rel.startswith(SYSTEM_EXCLUDE_PREFIXES):
            raise PackagePlanValidationError(f"System integrity manifest contains a non-packageable path: {rel}")
        digest = str(raw_entry.get("sha256") or "").lower()
        size = raw_entry.get("size_bytes")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise PackagePlanValidationError(f"System integrity manifest has invalid SHA-256 for: {rel}")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise PackagePlanValidationError(f"System integrity manifest has invalid size for: {rel}")
        entries[rel] = dict(raw_entry)
    if payload.get("file_count") != len(entries):
        raise PackagePlanValidationError("System integrity manifest file_count does not match its files list")
    return payload, entries


def _git_head_blob(root: Path, rel: str) -> bytes | None:
    """Return canonical HEAD bytes only when ``root`` is the exact Git repository."""
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=False, timeout=15,
        )
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
            return None
        blob = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{rel}"],
            capture_output=True, check=False, timeout=30,
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return None
    return bytes(blob.stdout) if blob.returncode == 0 else None


def _system_entry_bytes(root: Path, path: Path, rel: str, entry: Mapping[str, object]) -> bytes:
    raw_size = entry.get("size_bytes")
    if isinstance(raw_size, bool) or not isinstance(raw_size, int) or raw_size < 0:
        raise PackagePlanValidationError(f"Protected system file has invalid canonical size: {rel}")
    expected_size = raw_size
    expected_sha = str(entry.get("sha256") or "").lower()
    if len(expected_sha) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha):
        raise PackagePlanValidationError(f"Protected system file has invalid canonical SHA-256: {rel}")
    try:
        worktree_bytes = path.read_bytes()
    except OSError as exc:
        raise PackagePlanValidationError(f"Protected system file is missing or unreadable: {rel}") from exc
    if len(worktree_bytes) == expected_size and _sha256_bytes(worktree_bytes) == expected_sha:
        return worktree_bytes

    canonical = _git_head_blob(root, rel)
    if canonical is not None and len(canonical) == expected_size and _sha256_bytes(canonical) == expected_sha:
        return canonical
    raise PackagePlanValidationError(
        f"Protected system file bytes do not match the canonical integrity manifest: {rel}"
    )


def _package_local_system_manifest(
    canonical_manifest: Mapping[str, object],
    virtual_payloads: Mapping[str, bytes],
) -> bytes:
    payload = dict(canonical_manifest)
    raw_files = canonical_manifest.get("files")
    if not isinstance(raw_files, list):
        raise PackagePlanValidationError("System integrity manifest does not contain a files list")
    files = [dict(item) for item in raw_files if isinstance(item, dict)]
    seen = {str(item.get("path") or "") for item in files}
    for rel, raw in sorted(virtual_payloads.items()):
        if rel in seen or rel == SYSTEM_INTEGRITY_MANIFEST_NAME:
            raise PackagePlanValidationError(f"Virtual package path collides with protected system inventory: {rel}")
        files.append({
            "path": rel,
            "size_bytes": len(raw),
            "sha256": _sha256_bytes(raw),
            "mutable_runtime": False,
            "classification": "package_virtual_file",
            "archive": False,
            "hash_policy": "sha256_file_bytes",
        })
        seen.add(rel)
    files.sort(key=lambda item: str(item.get("path") or ""))
    payload["files"] = files
    payload["file_count"] = len(files)
    payload["static_file_count"] = len(files)
    payload["truth_boundary"] = (
        str(canonical_manifest.get("truth_boundary") or "").rstrip()
        + " Package-local virtual metadata is explicitly hashed into this transported manifest."
    ).strip()
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _normalize_package_rel(rel: str) -> str:
    return validate_safe_relative_path(str(rel))


def forbidden_package_reason(rel: str) -> str | None:
    try:
        rel = validate_safe_relative_path(str(rel))
    except UnsafeRelativePathError as exc:
        return str(exc)
    parts = set(Path(rel).parts)
    if "__pycache__" in parts:
        return "__pycache__ is never packaged"
    if ".pytest_cache" in parts:
        return ".pytest_cache is never packaged"
    if rel in FORBIDDEN_PACKAGE_EXACT:
        return "runtime/root marker is never packaged"
    if rel.startswith(FORBIDDEN_PACKAGE_PREFIXES):
        return "runtime or bridge queue directory is never packaged"
    if any(Path(rel).match(pattern) for pattern in FORBIDDEN_PACKAGE_GLOBS):
        return "forbidden runtime/cache pattern is never packaged"
    return None


def find_forbidden_package_paths(rel_paths) -> list[tuple[str, str]]:
    blocked: list[tuple[str, str]] = []
    for rel in rel_paths:
        raw = str(rel)
        reason = forbidden_package_reason(raw)
        if reason:
            blocked.append((raw, reason))
    return blocked


def validate_package_plan(
    rel_paths,
    *,
    root: Path | None = None,
    destination_root: Path | None = None,
) -> None:
    paths = [str(rel) for rel in rel_paths]
    blocked = find_forbidden_package_paths(paths)
    for raw in paths:
        try:
            canonical = validate_safe_relative_path(raw)
            if root is not None:
                resolve_safe_source(root, canonical)
            if destination_root is not None:
                resolve_safe_destination(destination_root, canonical)
        except UnsafeRelativePathError as exc:
            blocked.append((raw, str(exc)))
    if not blocked:
        return
    examples = ", ".join(f"{rel} ({reason})" for rel, reason in blocked[:10])
    more = "" if len(blocked) <= 10 else f"; +{len(blocked) - 10} more"
    raise PackagePlanValidationError(f"Forbidden paths in package plan: {examples}{more}")


def _is_common_excluded(path: Path, rel: str, output_zip: Path) -> bool:
    if path == output_zip:
        return True
    if forbidden_package_reason(rel):
        return True
    if any(part in COMMON_EXCLUDE_PARTS for part in path.parts):
        return True
    if rel.startswith("exports/"):
        return True
    return any(rel.endswith(suffix) for suffix in COMMON_EXCLUDE_SUFFIXES)


def private_generated_source_reason(path: Path, rel: str) -> str | None:
    """Return a blocking provenance reason for source-safe export candidates.

    The scanner intentionally checks exact known generated sources first and then
    a small, bounded text prefix. Marker literals are assembled from parts so the
    scanner implementation cannot match itself merely because it documents them.
    """
    rel = _normalize_package_rel(rel)
    if rel in GITHUB_SAFE_PRIVATE_EXACT:
        return "known_private_generated_source"
    if path.suffix.lower() not in {".py", ".json", ".jsonl", ".md", ".txt"}:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:262144].lower()
    except OSError:
        return "source_unreadable_for_privacy_scan"
    for left, right in _PRIVATE_MARKER_PARTS:
        marker = left + "_" + right
        if marker in text:
            return f"private_marker:{marker}"
    return None


def _iter_files(root: Path, mode: str, output_zip: Path):
    root = Path(root).resolve()
    output_zip = Path(output_zip).resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _is_common_excluded(path.resolve(), rel, output_zip):
            continue
        if mode == "system" and rel.startswith(SYSTEM_EXCLUDE_PREFIXES):
            continue
        if mode == "memory" and not rel.startswith("memory/"):
            continue
        if mode == "nlp" and not (rel.startswith(NLP_INCLUDE_PREFIXES) or rel in NLP_INCLUDE_EXACT):
            continue
        if mode == "github_source_safe":
            if rel.startswith(GITHUB_SAFE_EXCLUDE_PREFIXES):
                continue
            if private_generated_source_reason(path, rel):
                continue
        yield path, rel


def build_package_plan(root: Path, mode: str, output_zip: Path | None = None) -> list[tuple[Path, str]]:
    """Build the exact immutable-by-value plan used by preview and export."""
    root = Path(root).resolve()
    preview_output = Path(output_zip).resolve() if output_zip is not None else (root / "exports" / ".preview.zip").resolve()
    plan = list(_iter_files(root, mode, preview_output))
    validate_package_plan((rel for _, rel in plan), root=root)
    if mode == "github_source_safe":
        blocked = [
            {"path": rel, "reason": reason}
            for path, rel in plan
            if (reason := private_generated_source_reason(path, rel))
        ]
        if blocked:
            raise PackagePlanValidationError(
                "Private generated sources remain in source-safe plan: "
                + json.dumps(blocked[:10], ensure_ascii=False)
            )
    return plan


def _checkpoint_sqlite_databases(root: Path) -> list[str]:
    """Record active WAL files without blocking export.

    Transient WAL/SHM files are excluded from the archive. The note preserves
    the truth that a checkpoint was not forced while another process could be
    using a database.
    """
    notes: list[str] = []
    for db in sorted(Path(root).rglob("*.sqlite3")):
        try:
            rel = db.relative_to(root).as_posix()
        except Exception:
            rel = str(db)
        if forbidden_package_reason(rel):
            continue
        if any(part in COMMON_EXCLUDE_PARTS for part in db.parts):
            continue
        if Path(str(db) + "-wal").exists() or Path(str(db) + "-shm").exists():
            notes.append(f"Pominięto blokujący checkpoint WAL dla {rel}; transient WAL/SHM nie są pakowane.")
    return notes


def _unsafe_zip_entries(zf: zipfile.ZipFile) -> list[str]:
    try:
        validate_zip_resources(zf)
    except ZipResourceLimitError as exc:
        # The audit must be able to enumerate unsafe names in order to report
        # them. Resource exhaustion remains fatal; only path-policy failures
        # are converted into audit findings below.
        if not str(exc).startswith("unsafe_archive_member:"):
            raise
    unsafe: list[str] = []
    for info in zf.infolist():
        name = info.filename[:-1] if info.is_dir() and info.filename.endswith("/") else info.filename
        try:
            validate_safe_relative_path(name)
        except UnsafeRelativePathError:
            unsafe.append(info.filename)
            continue
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            unsafe.append(info.filename)
    return unsafe


def _extract_zip_safely(zf: zipfile.ZipFile, target: Path) -> list[str]:
    validate_zip_resources(zf)
    extracted: list[str] = []
    for info in zf.infolist():
        relative = info.filename[:-1] if info.is_dir() and info.filename.endswith("/") else info.filename
        canonical = validate_safe_relative_path(relative)
        destination = resolve_safe_destination(target, canonical)
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise PackagePlanValidationError(f"ZIP symlink is forbidden: {info.filename}")
        if info.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)
        extracted.append(canonical)
    return sorted(extracted)


def build_package_manifest(zip_path: Path, *, mode: str) -> dict:
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            validate_zip_resources(zf)
        except ZipResourceLimitError as exc:
            # A package manifest is also the input to the packing audit. Keep
            # unsafe member names observable so the audit can report them, but
            # continue to fail closed for actual resource-limit violations.
            if not str(exc).startswith("unsafe_archive_member:"):
                raise
        entries = [
            {
                "path": info.filename,
                "size_bytes": info.file_size,
                "compressed_size_bytes": info.compress_size,
                "crc32": f"{info.CRC:08x}",
                "is_dir": info.is_dir(),
            }
            for info in zf.infolist()
        ]
    return {
        "schema_version": f"package_manifest/{PACKAGE_VERSION}",
        "archive_name": zip_path.name,
        "archive_sha256": _sha256_file(zip_path),
        "mode": mode,
        "entry_count": len(entries),
        "entries": entries,
        "truth_boundary": "Manifest opisuje wpisy faktycznie zapisane w ZIP-ie; nie jest markerem aktywnego runtime.",
    }


def build_packing_audit(zip_path: Path, package_manifest: dict) -> dict:
    zip_path = Path(zip_path)
    errors: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [info.filename for info in zf.infolist()]
        unsafe = _unsafe_zip_entries(zf)
        forbidden = find_forbidden_package_paths(names)
        bad_crc = zf.testzip()
        if unsafe:
            errors.append("unsafe_paths")
        if forbidden:
            errors.append("forbidden_paths")
        if bad_crc:
            errors.append(f"crc_failure:{bad_crc}")
        extracted: list[str] = []
        extract_error = None
        if not errors:
            try:
                with tempfile.TemporaryDirectory(prefix="jazn_package_smoke_") as tmp:
                    target = Path(tmp)
                    extracted = _extract_zip_safely(zf, target)
            except Exception as exc:
                extract_error = f"{type(exc).__name__}: {exc}"
                errors.append("extract_smoke_failed")
        expected = sorted(
            entry["path"]
            for entry in package_manifest.get("entries", [])
            if not entry.get("is_dir")
        )
        extract_ok = extract_error is None and extracted == expected and not errors
    return {
        "schema_version": f"packing_audit/{PACKAGE_VERSION}",
        "archive_name": zip_path.name,
        "archive_sha256": _sha256_file(zip_path),
        "entry_count": len(package_manifest.get("entries", [])),
        "manifest_entry_count_matches": len(package_manifest.get("entries", [])) == len(names),
        "unsafe_paths": unsafe,
        "forbidden_paths": [{"path": path, "reason": reason} for path, reason in forbidden],
        "crc_ok": bad_crc is None,
        "crc_failure_entry": bad_crc,
        "extract_smoke_ok": extract_ok,
        "extract_error": extract_error,
        "errors": errors,
        "ok": not errors and bad_crc is None and extract_ok,
        "truth_boundary": "PACKING_AUDIT potwierdza transport ZIP, CRC, ścieżki i świeże rozpakowanie; nie potwierdza działania runtime.",
    }


def export_package(
    root: Path,
    mode: str,
    output_zip: Path | None = None,
    *,
    virtual_files: Mapping[str, str | bytes] | None = None,
) -> PackageExportReport:
    """Create a validated ZIP, optionally injecting verified virtual metadata.

    ``virtual_files`` exists for release metadata such as ``JAZN_DEPENDENCY_SET.json``.
    It never mutates the source tree; every virtual path is validated by the same
    fail-closed package path policy used for physical files.
    """
    root = Path(root).resolve()
    if mode not in {"system", "memory", "nlp", "github_source_safe", "full"}:
        raise ValueError("mode must be one of: system, memory, nlp, github_source_safe, full")
    exports_dir = root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if output_zip is None:
        output_zip = exports_dir / f"latka_jazn_{mode}_{stamp}.zip"
    else:
        output_zip = Path(output_zip)
        if not output_zip.is_absolute():
            output_zip = root / output_zip
        output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()

    notes: list[str] = []
    if mode in {"memory", "full"}:
        try:
            SessionContinuityManager(
                root,
                version=read_runtime_version_from_version_py(root, fallback="unknown") or "unknown",
            ).update_index(reason=f"export_{mode}", source="package_export.export_package")
            notes.append("Zaktualizowano session_continuity_index.json przed eksportem pamięci/pełnej paczki.")
        except Exception as exc:
            notes.append(f"Nie udało się odświeżyć session_continuity_index.json przed eksportem: {exc!r}")
        notes.extend(_checkpoint_sqlite_databases(root))

    file_count = 0
    total = 0
    virtual_payloads: dict[str, bytes] = {}
    for raw_name, raw_payload in sorted((virtual_files or {}).items()):
        name = validate_safe_relative_path(raw_name)
        if forbidden_package_reason(name):
            raise PackagePlanValidationError(f"Forbidden virtual package path: {name}")
        payload = raw_payload.encode("utf-8") if isinstance(raw_payload, str) else bytes(raw_payload)
        virtual_payloads[name] = payload
    system_entries: dict[str, dict] | None = None
    system_manifest_bytes: bytes | None = None
    if mode == "system":
        canonical_manifest, system_entries = _system_integrity_contract(root)
        package_plan = []
        for rel in sorted(system_entries):
            path = resolve_safe_source(root, rel)
            if not path.is_file():
                raise PackagePlanValidationError(f"Protected system file is missing: {rel}")
            package_plan.append((path, rel))
        manifest_path = resolve_safe_source(root, SYSTEM_INTEGRITY_MANIFEST_NAME)
        if not manifest_path.is_file():
            raise PackagePlanValidationError("System integrity manifest is missing")
        package_plan.append((manifest_path, SYSTEM_INTEGRITY_MANIFEST_NAME))
        validate_package_plan((rel for _, rel in package_plan), root=root)
        system_manifest_bytes = _package_local_system_manifest(canonical_manifest, virtual_payloads)
    else:
        package_plan = build_package_plan(root, mode, output_zip)

    physical_names = {rel for _, rel in package_plan}
    collisions = sorted((physical_names - {SYSTEM_INTEGRITY_MANIFEST_NAME}) & set(virtual_payloads))
    if collisions:
        raise PackagePlanValidationError(f"Virtual package paths collide with physical files: {collisions}")
    with zipfile.ZipFile(
        output_zip,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
        compresslevel=1,
    ) as zf:
        for path, rel in package_plan:
            compress_type = zipfile.ZIP_STORED if rel.endswith((".sqlite3", ".7z")) else zipfile.ZIP_DEFLATED
            if mode == "system":
                assert system_entries is not None and system_manifest_bytes is not None
                if rel == SYSTEM_INTEGRITY_MANIFEST_NAME:
                    raw = system_manifest_bytes
                else:
                    raw = _system_entry_bytes(root, path, rel, system_entries[rel])
                info = zipfile.ZipInfo.from_file(path, rel)
                info.compress_type = compress_type
                zf.writestr(info, raw)
                total += len(raw)
            else:
                zf.write(path, rel, compress_type=compress_type)
                total += path.stat().st_size
            file_count += 1
        for rel, payload in virtual_payloads.items():
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload)
            total += len(payload)
            file_count += 1

    if file_count == 0:
        notes.append("Paczka nie zawierała plików; sprawdź tryb eksportu i ścieżkę root.")
    if mode in {"memory", "full"}:
        continuity_index = root / "memory" / "raw" / "session_continuity_index.json"
        if continuity_index.exists():
            notes.append("Dołączono memory/raw/session_continuity_index.json oraz memory/layered/continuity.jsonl, jeśli istnieje; host-level workspace_runtime pozostaje poza paczką.")
        raw_chat = root / "memory" / "raw" / "chat.html"
        if raw_chat.exists():
            notes.append(f"Dołączono jawny memory/raw/chat.html ({raw_chat.stat().st_size} B).")
        else:
            notes.append("Nie znaleziono memory/raw/chat.html; runtime nie rozpakowuje archiwów 7z.")
    if mode == "system":
        notes.append("Eksport system-only celowo pomija memory/ oraz workspace_runtime/.")
    if mode == "nlp":
        notes.append("Eksport NLP-resources-only zawiera adaptery i lekkie zasoby NLP; nie zawiera pamięci ani ciężkich modeli.")
    if mode == "github_source_safe":
        notes.append("Eksport github-source-safe pomija cały katalog memory/, workspace_runtime/, surowe czaty i aktywne bazy SQLite.")

    package_manifest = build_package_manifest(output_zip, mode=mode)
    packing_audit = build_packing_audit(output_zip, package_manifest)
    package_manifest_path = output_zip.with_name(output_zip.name + ".package_manifest.json")
    packing_audit_path = output_zip.with_name(output_zip.name + ".PACKING_AUDIT.json")
    package_manifest_text = json.dumps(package_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    packing_audit_text = json.dumps(packing_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    package_manifest_path.write_text(package_manifest_text, encoding="utf-8")
    packing_audit_path.write_text(packing_audit_text, encoding="utf-8")
    (output_zip.parent / "package_manifest.json").write_text(package_manifest_text, encoding="utf-8")
    (output_zip.parent / "PACKING_AUDIT.json").write_text(packing_audit_text, encoding="utf-8")
    if not packing_audit["ok"]:
        raise PackagePlanValidationError(
            "Packing audit failed: " + ", ".join(packing_audit.get("errors") or ["unknown_error"])
        )

    report = PackageExportReport(
        mode=mode,
        output_zip=str(output_zip),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        file_count=file_count,
        total_uncompressed_bytes=total,
        zip_size_bytes=output_zip.stat().st_size,
        sha256=_sha256_file(output_zip),
        includes_memory=mode in {"memory", "full"},
        includes_system=mode in {"system", "nlp", "github_source_safe", "full"},
        package_manifest_path=str(package_manifest_path),
        packing_audit_path=str(packing_audit_path),
        crc_ok=bool(packing_audit["crc_ok"]),
        extract_smoke_ok=bool(packing_audit["extract_smoke_ok"]),
        notes=notes,
    )
    report_path = output_zip.with_suffix(".report.json")
    report_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def export_package_json(root: Path, mode: str, output_zip: Path | None = None) -> str:
    return json.dumps(
        export_package(root, mode, output_zip).to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
