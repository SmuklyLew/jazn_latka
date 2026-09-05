from __future__ import annotations

from dataclasses import dataclass, replace
import fnmatch
import hashlib
from pathlib import Path, PurePosixPath
import shlex
import shutil
from threading import Event
from typing import Callable

from .errors import PackIntegrityError, PackValidationError
from .models import PackPlan, ProgressEvent, SourceEntry

ProgressCallback = Callable[[ProgressEvent], None]
_CHUNK_SIZE = 4 * 1024 * 1024
_SAMPLE_SIZE = 64 * 1024
_EOL_WARNING_SAMPLE_LIMIT = 100


@dataclass(frozen=True, slots=True)
class AttributeState:
    text: bool | str | None = None
    eol: str | None = None


@dataclass(frozen=True, slots=True)
class StagingResult:
    plan: PackPlan
    member_sha256: dict[str, str]
    eol_checked_count: int
    eol_skipped_count: int
    eol_warning_paths: tuple[str, ...] = ()
    staging_mode: str = "source-folder-byte-copy"

    def verification_metadata(self) -> dict[str, object]:
        return {
            "staging_mode": self.staging_mode,
            "byte_exact_source_copy": True,
            "eol_policy": "diagnostic_only",
            "eol_checked_count": self.eol_checked_count,
            "eol_skipped_count": self.eol_skipped_count,
            "eol_warning_count": len(self.eol_warning_paths),
            "eol_warning_sample": list(self.eol_warning_paths[:_EOL_WARNING_SAMPLE_LIMIT]),
        }


def _emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    if callback is not None:
        callback(event)


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        from .errors import PackCancelled

        raise PackCancelled("Operacja została anulowana.")


def _pattern_matches(pattern: str, path: PurePosixPath) -> bool:
    normalized = path.as_posix()
    if "/" not in pattern:
        return fnmatch.fnmatchcase(path.name, pattern)
    return fnmatch.fnmatchcase(normalized, pattern)


def _parse_attributes_line(line: str) -> tuple[str, list[str]] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    try:
        tokens = shlex.split(stripped, comments=True, posix=True)
    except ValueError as exc:
        raise PackValidationError(f"Niepoprawna linia .gitattributes: {line!r}: {exc}") from exc
    if len(tokens) < 2:
        return None
    return tokens[0], tokens[1:]


def _load_attribute_rules(source_root: Path) -> list[tuple[str, list[str]]]:
    """Load optional Git EOL policy for diagnostics only.

    A folder snapshot must remain packageable even when it is not a Git checkout.
    When .gitattributes exists, its EOL policy is reported as a warning surface;
    it never changes source bytes and never blocks a valid folder snapshot.
    """

    attributes_path = source_root / ".gitattributes"
    if not attributes_path.is_file():
        return []
    try:
        lines = attributes_path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise PackValidationError(f".gitattributes nie jest poprawnym UTF-8: {exc}") from exc
    rules: list[tuple[str, list[str]]] = []
    for line in lines:
        parsed = _parse_attributes_line(line)
        if parsed is not None:
            rules.append(parsed)
    return rules


def attribute_state_for_path(
    path: PurePosixPath,
    rules: list[tuple[str, list[str]]],
) -> AttributeState:
    text: bool | str | None = None
    eol: str | None = None
    for pattern, attributes in rules:
        if not _pattern_matches(pattern, path):
            continue
        for token in attributes:
            if token == "binary":
                text = False
                continue
            if token == "text":
                text = True
                continue
            if token == "text=auto":
                text = "auto"
                continue
            if token == "-text":
                text = False
                continue
            if token == "!text":
                text = None
                continue
            if token.startswith("eol="):
                value = token.split("=", 1)[1].strip().casefold()
                if value in {"lf", "crlf"}:
                    eol = value
                continue
            if token == "!eol":
                eol = None
    return AttributeState(text=text, eol=eol)


def _looks_text(sample: bytes) -> bool:
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _inspect_eol_stream(source: Path, expected: str, *, auto_text: bool) -> bool | None:
    """Return True/False for EOL conformity, or None when auto-text is binary.

    This is intentionally diagnostic. Integrity is defined by preserving the
    actual source bytes and matching their SHA-256 after reading them from ZIP.
    """

    with source.open("rb") as handle:
        sample = handle.read(_SAMPLE_SIZE)
        if auto_text and not _looks_text(sample):
            return None
        handle.seek(0)
        pending_cr = False
        while True:
            chunk = handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            if expected == "lf":
                if b"\r" in chunk:
                    return False
                continue
            if expected != "crlf":
                return True
            for value in chunk:
                if pending_cr:
                    if value != 0x0A:
                        return False
                    pending_cr = False
                    continue
                if value == 0x0D:
                    pending_cr = True
                elif value == 0x0A:
                    return False
        if expected == "crlf" and pending_cr:
            return False
    return True


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_byte_exact(
    source: Path,
    target: Path,
    *,
    expected_size: int,
    callback: ProgressCallback | None,
    cancel_event: Event | None,
    archive_path: str,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    digest = hashlib.sha256()
    written = 0
    with source.open("rb") as src, target.open("wb") as dst:
        while True:
            _check_cancel(cancel_event)
            chunk = src.read(_CHUNK_SIZE)
            if not chunk:
                break
            dst.write(chunk)
            digest.update(chunk)
            written += len(chunk)
            _emit(
                callback,
                ProgressEvent(
                    "staging",
                    "Source folder byte-exact staging",
                    written,
                    expected_size,
                    archive_path,
                ),
            )
    after = source.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise PackIntegrityError(f"Źródło zmieniło się podczas stagingu: {archive_path}")
    if written != expected_size or written != before.st_size:
        raise PackIntegrityError(
            f"Rozmiar źródła zmienił się od skanowania: {archive_path}: plan={expected_size}, staged={written}."
        )
    staged_digest = _sha256_path(target)
    source_digest = digest.hexdigest()
    if staged_digest != source_digest:
        raise PackIntegrityError(f"Staging nie jest byte-exact dla: {archive_path}")
    shutil.copystat(source, target, follow_symlinks=False)
    return source_digest


def materialize_source_staging(
    plan: PackPlan,
    destination: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> StagingResult:
    """Copy the approved folder plan byte-for-byte into temporary staging.

    .gitattributes is advisory here: it can diagnose EOL drift but it does not
    define archive bytes. The selected folder and approved exclusion policy do.
    """

    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    source_root = plan.request.source_root.resolve()
    rules = _load_attribute_rules(source_root) if plan.request.content.value != "memory" else []

    staged_entries: list[SourceEntry] = []
    member_sha256: dict[str, str] = {}
    eol_checked = 0
    eol_skipped = 0
    eol_warnings: list[str] = []

    for entry in plan.entries:
        _check_cancel(cancel_event)
        target = destination / Path(*PurePosixPath(entry.archive_path.rstrip("/")).parts)
        if entry.is_dir:
            target.mkdir(parents=True, exist_ok=True)
            staged_entries.append(replace(entry, source=target))
            continue

        expected_eol: str | None = None
        auto_text = False
        try:
            relative_source = entry.source.resolve().relative_to(source_root)
        except ValueError:
            relative_source = None
        if relative_source is not None and not entry.archive_path.startswith("memory/") and rules:
            state = attribute_state_for_path(PurePosixPath(relative_source.as_posix()), rules)
            expected_eol = state.eol if state.text is not False else None
            auto_text = state.text == "auto"

        if expected_eol in {"lf", "crlf"}:
            observed = _inspect_eol_stream(entry.source, expected_eol, auto_text=auto_text)
            if observed is None:
                eol_skipped += 1
            else:
                eol_checked += 1
                if observed is False:
                    eol_warnings.append(entry.archive_path)
        else:
            eol_skipped += 1

        digest = _copy_byte_exact(
            entry.source,
            target,
            expected_size=entry.size_bytes,
            callback=callback,
            cancel_event=cancel_event,
            archive_path=entry.archive_path,
        )
        member_sha256[entry.archive_path] = digest
        staged_entries.append(replace(entry, source=target))

    staged_plan = replace(plan, entries=tuple(staged_entries))
    return StagingResult(
        plan=staged_plan,
        member_sha256=member_sha256,
        eol_checked_count=eol_checked,
        eol_skipped_count=eol_skipped,
        eol_warning_paths=tuple(eol_warnings),
    )


def materialize_canonical_staging(
    plan: PackPlan,
    destination: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> StagingResult:
    """Compatibility alias for callers from generator 10.1.86.0.112."""

    return materialize_source_staging(
        plan,
        destination,
        callback=callback,
        cancel_event=cancel_event,
    )
