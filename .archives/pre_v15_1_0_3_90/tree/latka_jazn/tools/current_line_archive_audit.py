from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from latka_jazn.version import DISTRIBUTION_VERSION, PACKAGE_VERSION, PACKAGE_VERSION_FULL, schema_version, version_number

SCHEMA_VERSION = schema_version("current_line_archive_audit")
ARCHIVE_ROOT = Path(".archives/pre_v15_1_0_3_89")
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".ps1", ".sh", ".bat", ".cmd", ".xml", ".csv",
}
EXCLUDED_ACTIVE_PATHS = {
    "PACKAGE_INTEGRITY_MANIFEST.json",
    "SOURCE_PROVENANCE.json",
}
_VERSION_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])v?(?P<version>1[45](?:[._]\d+){2,6})(?![A-Za-z0-9])"
)


def _run_git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _version_tuple(raw: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in raw.replace("_", ".").lstrip("vV").split("."))
    except (TypeError, ValueError):
        return None


def _padded(parts: tuple[int, ...], width: int = 7) -> tuple[int, ...]:
    return (parts + (0,) * width)[:width]


def _is_old_package_version(raw: str) -> bool:
    candidate = _version_tuple(raw)
    current = _version_tuple(version_number(PACKAGE_VERSION))
    if candidate is None or current is None:
        return False
    if candidate[0] not in {14, 15}:
        return False
    return _padded(candidate) < _padded(current)


def _tracked_paths(root: Path) -> list[str]:
    return [item for item in _run_git(root, "ls-files", "-z").split("\0") if item]


def _is_active_path(path: str) -> bool:
    folded = path.replace("\\", "/")
    return not folded.startswith(".archives/") and folded not in EXCLUDED_ACTIVE_PATHS


def _line_is_canonical_distribution(path: str, line: str, raw_version: str) -> bool:
    return (
        "DISTRIBUTION_VERSION" in line
        and raw_version.replace("_", ".").lstrip("vV") == DISTRIBUTION_VERSION
    )


def scan_active_old_references(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rel in _tracked_paths(root):
        if not _is_active_path(rel):
            continue
        path = root / rel
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in _VERSION_RE.finditer(line):
                raw = match.group("version")
                if not _is_old_package_version(raw):
                    continue
                if _line_is_canonical_distribution(rel, line, raw):
                    continue
                findings.append(
                    {
                        "path": rel,
                        "line": lineno,
                        "version": raw.replace("_", "."),
                        "token_sha256": hashlib.sha256(match.group(0).encode("utf-8")).hexdigest(),
                        "line_sha256": hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest(),
                    }
                )
    return findings


def validate_archive(root: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    archive_root = root / ARCHIVE_ROOT
    manifest_path = archive_root / "ARCHIVE_MANIFEST.json"
    if not manifest_path.is_file():
        return ["archive_manifest_missing"], {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"archive_manifest_invalid:{exc}"], {}
    entries = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        return ["archive_manifest_files_not_list"], manifest
    exact_count = 0
    metadata_only_count = 0
    seen_originals: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            issues.append("archive_entry_not_object")
            continue
        original = str(entry.get("original_path") or "")
        retention = str(entry.get("retention") or "")
        if not original or original in seen_originals:
            issues.append(f"archive_original_invalid_or_duplicate:{original}")
            continue
        seen_originals.add(original)
        expected_sha = str(entry.get("sha256") or "")
        expected_size = entry.get("size_bytes")
        archive_path = entry.get("archive_path")
        if retention == "metadata_only_private_source":
            metadata_only_count += 1
            if archive_path is not None:
                issues.append(f"private_entry_must_not_have_archive_path:{original}")
            if original != "latka_jazn/contracts/embedded_sources.py":
                issues.append(f"unexpected_metadata_only_entry:{original}")
            continue
        if retention != "exact_copy":
            issues.append(f"unknown_retention:{original}:{retention}")
            continue
        exact_count += 1
        if not archive_path:
            issues.append(f"archive_path_missing:{original}")
            continue
        archived = root / str(archive_path)
        if not archived.is_file():
            issues.append(f"archive_file_missing:{archive_path}")
            continue
        data = archived.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha:
            issues.append(f"archive_sha_mismatch:{archive_path}")
        if len(data) != expected_size:
            issues.append(f"archive_size_mismatch:{archive_path}")
    if exact_count != manifest.get("exact_copy_count"):
        issues.append("archive_exact_copy_count_mismatch")
    if metadata_only_count != manifest.get("metadata_only_private_count"):
        issues.append("archive_metadata_only_count_mismatch")
    if len(entries) != manifest.get("file_count"):
        issues.append("archive_file_count_mismatch")
    if (root / "latka_jazn/contracts/embedded_sources.py").exists():
        issues.append("embedded_private_source_still_active")
    return issues, manifest


@dataclass(slots=True)
class CurrentLineArchiveAudit:
    schema_version: str
    ok: bool
    package_version: str
    package_version_full: str
    source_commit: str
    active_old_reference_count: int
    active_old_references: list[dict[str, Any]]
    archive_file_count: int
    archive_exact_copy_count: int
    archive_metadata_only_private_count: int
    archive_issues: list[str]
    truth_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_audit(root: str | Path) -> CurrentLineArchiveAudit:
    runtime_root = Path(root).expanduser().resolve()
    findings = scan_active_old_references(runtime_root)
    archive_issues, manifest = validate_archive(runtime_root)
    try:
        source_commit = _run_git(runtime_root, "rev-parse", "HEAD").strip()
    except RuntimeError:
        source_commit = "git_unavailable"
    return CurrentLineArchiveAudit(
        schema_version=SCHEMA_VERSION,
        ok=not findings and not archive_issues,
        package_version=PACKAGE_VERSION,
        package_version_full=PACKAGE_VERSION_FULL,
        source_commit=source_commit,
        active_old_reference_count=len(findings),
        active_old_references=findings,
        archive_file_count=int(manifest.get("file_count") or 0),
        archive_exact_copy_count=int(manifest.get("exact_copy_count") or 0),
        archive_metadata_only_private_count=int(manifest.get("metadata_only_private_count") or 0),
        archive_issues=archive_issues,
        truth_boundary=(
            "Audyt sprawdza śledzone aktywne pliki tekstowe i integralność archiwum. "
            "Nie interpretuje zawartości prywatnego embedded source; zachowuje wyłącznie jego metadane."
        ),
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_audit(args.root)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"ok={report.ok} package={report.package_version} "
            f"active_old_refs={report.active_old_reference_count} "
            f"archive_files={report.archive_file_count} issues={len(report.archive_issues)}"
        )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
