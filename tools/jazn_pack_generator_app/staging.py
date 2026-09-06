from __future__ import annotations

from dataclasses import dataclass, replace
import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
from threading import Event
from typing import Callable

from .errors import PackCancelled, PackIntegrityError
from .models import PackPlan, ProgressEvent, SourceEntry

ProgressCallback = Callable[[ProgressEvent], None]
_CHUNK = 4 * 1024 * 1024
_SAMPLE = 64 * 1024


@dataclass(frozen=True, slots=True)
class AttributeState:
    text: bool | str | None = None
    eol: str | None = None


@dataclass(frozen=True, slots=True)
class StagingResult:
    plan: PackPlan
    member_sha256: dict[str, str]
    eol_checked_count: int = 0
    eol_skipped_count: int = 0
    eol_warning_paths: tuple[str, ...] = ()
    staging_mode: str = "source-folder-byte-copy"
    canonical_release_bytes: bool = False
    release_report: dict[str, object] | None = None

    def verification_metadata(self) -> dict[str, object]:
        if self.canonical_release_bytes:
            report = dict(self.release_report or {})
            return {
                "staging_mode": self.staging_mode,
                "byte_exact_source_copy": False,
                "canonical_release_bytes": True,
                "eol_policy": "canonical_git_blobs_fail_closed",
                "eol_checked_count": self.eol_checked_count,
                "eol_skipped_count": self.eol_skipped_count,
                "eol_warning_count": 0,
                "eol_warning_sample": [],
                "release_source_commit": report.get("source_commit"),
                "release_source_tree": report.get("source_tree"),
                "release_status": report.get("status"),
            }
        return {
            "staging_mode": self.staging_mode,
            "byte_exact_source_copy": True,
            "canonical_release_bytes": False,
            "eol_policy": "diagnostic_only",
            "eol_checked_count": self.eol_checked_count,
            "eol_skipped_count": self.eol_skipped_count,
            "eol_warning_count": len(self.eol_warning_paths),
            "eol_warning_sample": list(self.eol_warning_paths[:100]),
        }


def _cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise PackCancelled("Operacja została anulowana.")


def _emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    if callback is not None:
        callback(event)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_exact(
    source: Path,
    target: Path,
    *,
    expected_size: int,
    archive_path: str,
    callback: ProgressCallback | None,
    cancel_event: Event | None,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    digest = hashlib.sha256()
    written = 0
    with source.open("rb") as src, target.open("wb") as dst:
        while True:
            _cancel(cancel_event)
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            dst.write(chunk)
            digest.update(chunk)
            written += len(chunk)
            _emit(callback, ProgressEvent("staging", "Source folder byte-exact staging", written, expected_size, archive_path))
    after = source.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise PackIntegrityError(f"Źródło zmieniło się podczas stagingu: {archive_path}")
    if written != expected_size or written != before.st_size:
        raise PackIntegrityError(f"Rozmiar źródła zmienił się od skanowania: {archive_path}")
    observed = digest.hexdigest()
    if _sha(target) != observed:
        raise PackIntegrityError(f"Staging nie jest byte-exact dla: {archive_path}")
    shutil.copystat(source, target, follow_symlinks=False)
    return observed


def _parse_rules(root: Path) -> list[tuple[str, list[str]]]:
    path = root / ".gitattributes"
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return []
    rules: list[tuple[str, list[str]]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            tokens = shlex.split(stripped, comments=True, posix=True)
        except ValueError:
            continue
        if len(tokens) >= 2:
            rules.append((tokens[0], tokens[1:]))
    return rules


def attribute_state_for_path(path: PurePosixPath, rules: list[tuple[str, list[str]]]) -> AttributeState:
    text: bool | str | None = None
    eol: str | None = None
    normalized = path.as_posix()
    for pattern, attrs in rules:
        matched = fnmatch.fnmatchcase(path.name if "/" not in pattern else normalized, pattern)
        if not matched:
            continue
        for token in attrs:
            if token == "binary" or token == "-text":
                text = False
            elif token == "text":
                text = True
            elif token == "text=auto":
                text = "auto"
            elif token == "!text":
                text = None
            elif token.startswith("eol=") and token[4:].casefold() in {"lf", "crlf"}:
                eol = token[4:].casefold()
            elif token == "!eol":
                eol = None
    return AttributeState(text=text, eol=eol)


def _eol_conforms(path: Path, expected: str, auto_text: bool) -> bool | None:
    data = path.read_bytes()
    if auto_text:
        sample = data[:_SAMPLE]
        if b"\x00" in sample:
            return None
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if expected == "lf":
        return b"\r" not in data
    if expected == "crlf":
        normalized = data.replace(b"\r\n", b"")
        return b"\r" not in normalized and b"\n" not in normalized
    return True


def materialize_source_staging(
    plan: PackPlan,
    destination: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> StagingResult:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    source_root = plan.request.source_root.resolve()
    rules = _parse_rules(source_root) if plan.request.content.value != "memory" else []
    entries: list[SourceEntry] = []
    hashes: dict[str, str] = {}
    checked = skipped = 0
    warnings: list[str] = []
    for entry in plan.entries:
        _cancel(cancel_event)
        target = destination / Path(*PurePosixPath(entry.archive_path.rstrip("/")).parts)
        if entry.is_dir:
            target.mkdir(parents=True, exist_ok=True)
            entries.append(replace(entry, source=target))
            continue
        expected: str | None = None
        auto = False
        try:
            relative = entry.source.resolve().relative_to(source_root)
        except ValueError:
            relative = None
        if relative is not None and not entry.archive_path.startswith("memory/") and rules:
            state = attribute_state_for_path(PurePosixPath(relative.as_posix()), rules)
            expected = state.eol if state.text is not False else None
            auto = state.text == "auto"
        if expected:
            result = _eol_conforms(entry.source, expected, auto)
            if result is None:
                skipped += 1
            else:
                checked += 1
                if not result:
                    warnings.append(entry.archive_path)
        else:
            skipped += 1
        hashes[entry.archive_path] = _copy_exact(entry.source, target, expected_size=entry.size_bytes, archive_path=entry.archive_path, callback=callback, cancel_event=cancel_event)
        entries.append(replace(entry, source=target))
    return StagingResult(replace(plan, entries=tuple(entries)), hashes, checked, skipped, tuple(warnings))


def _run_release_staging(source_root: Path, destination: Path) -> dict[str, object]:
    from latka_jazn.tools.release_staging import create_release_staging, create_system_smoke_staging
    if (source_root / ".git").exists():
        return dict(create_release_staging(source_root, destination))
    return dict(create_system_smoke_staging(source_root, destination))


def _canonical_system_entries(destination: Path) -> tuple[list[SourceEntry], dict[str, str]]:
    manifest_path = destination / "PACKAGE_INTEGRITY_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackIntegrityError(f"Nie można odczytać kanonicznego manifestu SYSTEM: {exc}") from exc
    rows = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(rows, list):
        raise PackIntegrityError("Kanoniczny PACKAGE_INTEGRITY_MANIFEST.json nie zawiera listy files.")
    entries: list[SourceEntry] = []
    hashes: dict[str, str] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PackIntegrityError("Niepoprawny wpis files w kanonicznym manifeście SYSTEM.")
        rel = str(row.get("path") or "").replace("\\", "/").strip("/")
        if not rel or rel in seen:
            raise PackIntegrityError(f"Niepoprawny lub zduplikowany path w manifeście SYSTEM: {rel!r}")
        source = destination / Path(*PurePosixPath(rel).parts)
        expected_sha = str(row.get("sha256") or "").lower()
        try:
            expected_size = int(row.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise PackIntegrityError(f"Niepoprawny rozmiar w manifeście SYSTEM: {rel!r}") from exc
        if not source.is_file() or source.stat().st_size != expected_size or _sha(source) != expected_sha:
            raise PackIntegrityError(f"Kanoniczny staging nie zgadza się z manifestem dla {rel}")
        seen.add(rel)
        entries.append(SourceEntry(source, rel, expected_size, False))
        hashes[rel] = expected_sha
    if "PACKAGE_INTEGRITY_MANIFEST.json" not in seen:
        digest = _sha(manifest_path)
        entries.append(SourceEntry(manifest_path, "PACKAGE_INTEGRITY_MANIFEST.json", manifest_path.stat().st_size, False))
        hashes["PACKAGE_INTEGRITY_MANIFEST.json"] = digest
    return entries, hashes


def materialize_canonical_staging(
    plan: PackPlan,
    destination: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> StagingResult:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report = _run_release_staging(plan.request.source_root.resolve(), destination)
    system_entries, hashes = _canonical_system_entries(destination)
    entries = list(system_entries)
    for entry in plan.entries:
        if not entry.archive_path.startswith("memory/"):
            continue
        _cancel(cancel_event)
        target = destination / Path(*PurePosixPath(entry.archive_path.rstrip("/")).parts)
        if entry.is_dir:
            target.mkdir(parents=True, exist_ok=True)
            entries.append(replace(entry, source=target))
            continue
        hashes[entry.archive_path] = _copy_exact(entry.source, target, expected_size=entry.size_bytes, archive_path=entry.archive_path, callback=callback, cancel_event=cancel_event)
        entries.append(replace(entry, source=target))
    staged_plan = replace(plan, entries=tuple(entries), source_total_size_bytes=sum(e.size_bytes for e in entries if not e.is_dir))
    return StagingResult(
        staged_plan,
        hashes,
        eol_checked_count=0,
        eol_skipped_count=len(system_entries),
        staging_mode="canonical-release-staging",
        canonical_release_bytes=True,
        release_report=report,
    )
