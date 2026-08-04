from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
import uuid
import zipfile

from latka_jazn.packaging.zip_resource_limits import validate_zip_resources
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from latka_jazn.tools.console_progress import TerminalProgress, add_progress_arguments

CHUNK_SIZE = 8 * 1024 * 1024
SUPPORTED_PACKAGE_SET_SCHEMAS = frozenset({"jazn_package_set/v1", "jazn_package_set/v2"})


@dataclass(slots=True)
class PackagePartExpectation:
    part_no: int
    filename: str
    size_bytes: int | None = None
    sha256: str | None = None


def sanitize_zip_name(name: str) -> str:
    raw = str(name or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("Nazwa ZIP nie może być pusta.")
    if any(ch in raw for ch in '\\/:*?"<>|'):
        raise ValueError(f"Nazwa ZIP zawiera niedozwolone znaki: {raw!r}")
    if not raw.lower().endswith(".zip"):
        raw += ".zip"
    return raw


def sha256_file(path: Path, *, chunk_size: int = CHUNK_SIZE) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _crc32_file(path: Path) -> int:
    crc = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            crc = zlib.crc32(chunk, crc)
    return crc & 0xFFFFFFFF


def parse_sha256sum_file(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    path = Path(path)
    if not path.exists() or not path.is_file():
        return rows

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", raw)
        if not match:
            continue
        rows.append((match.group(1).lower(), _safe_part_filename(match.group(2).strip())))
    return rows


def _safe_part_filename(value: str) -> str:
    """Package volumes are always flat files next to their sidecars."""

    raw = str(value or "").strip()
    if (
        not raw
        or raw in {".", ".."}
        or "\x00" in raw
        or "/" in raw
        or "\\" in raw
        or Path(raw).name != raw
    ):
        raise ValueError(f"Niebezpieczna nazwa części paczki: {value!r}")
    return raw


def _read_package_sidecar(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("package.json paczki nie jest obiektem JSON")
    schema_version = str(payload.get("schema_version") or "").strip()
    if schema_version not in SUPPORTED_PACKAGE_SET_SCHEMAS:
        raise ValueError(
            "Nieobsługiwany schema_version package.json paczki: "
            f"{payload.get('schema_version')!r}"
        )
    return payload


def _find_package_sidecar(parts_dir: Path, base_zip_name: str) -> tuple[Path | None, dict[str, Any] | None]:
    exact = parts_dir / f"{base_zip_name}.package.json"
    if exact.is_file():
        return exact, _read_package_sidecar(exact)

    matches: list[tuple[Path, dict[str, Any]]] = []
    for candidate in sorted(parts_dir.glob("*.json")):
        if candidate == exact or ".package" not in candidate.name:
            continue
        try:
            payload = _read_package_sidecar(candidate)
            declared_name = sanitize_zip_name(str(payload.get("package_name") or ""))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if declared_name == base_zip_name:
            matches.append((candidate, payload))
    if len(matches) > 1:
        raise ValueError(
            "Niejednoznaczne sidecary package.json dla paczki "
            f"{base_zip_name!r}: " + ", ".join(path.name for path, _ in matches)
        )
    return matches[0] if matches else (None, None)


def load_package_set_metadata(parts_dir: Path, base_zip_name: str) -> dict[str, Any]:
    """Read the current package-set contract, with an explicit legacy fallback."""

    parts_dir = Path(parts_dir).expanduser().resolve()
    base_zip_name = sanitize_zip_name(base_zip_name)
    current_path, payload = _find_package_sidecar(parts_dir, base_zip_name)
    legacy_path = parts_dir / f"{base_zip_name}.manifest.json"
    if current_path is not None and payload is not None:
        declared_name = sanitize_zip_name(str(payload.get("package_name") or base_zip_name))
        if declared_name != base_zip_name:
            raise ValueError(
                f"package.json wskazuje inną paczkę: {declared_name!r} != {base_zip_name!r}"
            )
        archive_format = str(payload.get("archive_format") or "").strip().lower()
        if archive_format not in {"binary", "independent"}:
            raise ValueError(f"Nieobsługiwany archive_format paczki: {archive_format!r}")
        return {
            "source": "package.json",
            "path": str(current_path),
            "profile": str(payload.get("profile") or "unknown").strip().lower(),
            "archive_format": archive_format,
            "package_version": str(payload.get("package_version") or "").strip() or None,
            "schema_version": payload.get("schema_version"),
        }
    if legacy_path.is_file():
        return {
            "source": "legacy_manifest",
            "path": str(legacy_path),
            "profile": "unknown",
            "archive_format": "binary",
            "package_version": None,
            "schema_version": None,
        }
    return {
        "source": "filesystem_fallback",
        "path": None,
        "profile": "unknown",
        "archive_format": "binary",
        "package_version": None,
        "schema_version": None,
    }


def infer_base_zip_name(parts_dir: Path, base_zip_name: str | None = None) -> str:
    parts_dir = Path(parts_dir).expanduser().resolve()

    if base_zip_name:
        return sanitize_zip_name(base_zip_name)

    current_sidecars = sorted(parts_dir.glob("*.zip.package.json"))
    legacy_sidecars = sorted(parts_dir.glob("*.zip.manifest.json"))
    sidecar_names = {
        path.name[: -len(".package.json")]
        for path in current_sidecars
    } | {
        path.name[: -len(".manifest.json")]
        for path in legacy_sidecars
    }
    for candidate in sorted(parts_dir.glob("*.json")):
        if candidate in current_sidecars or ".package" not in candidate.name:
            continue
        try:
            payload = _read_package_sidecar(candidate)
            declared_name = sanitize_zip_name(str(payload.get("package_name") or ""))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            continue
        sidecar_names.add(declared_name)
    if len(sidecar_names) == 1:
        return next(iter(sidecar_names))

    groups: dict[str, int] = {}
    for part in parts_dir.glob("*.zip.[0-9][0-9][0-9]"):
        base = part.name[:-4]
        groups[base] = groups.get(base, 0) + 1

    if len(groups) == 1:
        return next(iter(groups))

    if not sidecar_names and not groups:
        raise FileNotFoundError(f"Nie znaleziono części ZIP w folderze: {parts_dir}")

    raise ValueError(
        "W folderze jest więcej niż jedna możliwa paczka. "
        "Podaj nazwę przez base_zip_name / --zip-name."
    )


def load_package_expectations(
    parts_dir: Path,
    base_zip_name: str,
) -> tuple[list[PackagePartExpectation], str | None, str]:
    parts_dir = Path(parts_dir).expanduser().resolve()
    base_zip_name = sanitize_zip_name(base_zip_name)

    package_path, package_payload = _find_package_sidecar(parts_dir, base_zip_name)
    manifest_path = parts_dir / f"{base_zip_name}.manifest.json"
    parts_sha_path = parts_dir / f"{base_zip_name}.parts.sha256"
    full_sha_path = parts_dir / f"{base_zip_name}.sha256"

    expected: list[PackagePartExpectation] = []
    expected_full_sha: str | None = None
    source = "glob"

    if package_path is not None and package_payload is not None:
        source = "package.json"
        data = package_payload
        expected_full_sha = str(data.get("logical_zip_sha256") or "").strip().lower() or None
        for item in data.get("outputs") or []:
            if not isinstance(item, dict):
                raise ValueError("package.json zawiera niepoprawny rekord outputs")
            expected.append(
                PackagePartExpectation(
                    part_no=int(item["part_no"]),
                    filename=_safe_part_filename(str(item["filename"])),
                    size_bytes=int(item["size_bytes"]) if item.get("size_bytes") is not None else None,
                    sha256=str(item.get("sha256") or "").strip().lower() or None,
                )
            )
    elif manifest_path.exists():
        source = "manifest"
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        expected_full_sha = str(
            data.get("logical_full_zip_sha256") or data.get("logical_zip_sha256") or ""
        ).strip().lower() or None

        for item in data.get("parts") or []:
            expected.append(
                PackagePartExpectation(
                    part_no=int(item["part_no"]),
                    filename=_safe_part_filename(str(item["filename"])),
                    size_bytes=int(item["size_bytes"]) if item.get("size_bytes") is not None else None,
                    sha256=str(item.get("sha256") or "").strip().lower() or None,
                )
            )

    elif parts_sha_path.exists():
        source = "parts.sha256"
        for part_no, (digest, filename) in enumerate(parse_sha256sum_file(parts_sha_path), start=1):
            expected.append(
                PackagePartExpectation(
                    part_no=part_no,
                    filename=filename,
                    sha256=digest,
                )
            )

    if not expected:
        for part_no, path in enumerate(sorted(parts_dir.glob(f"{base_zip_name}.[0-9][0-9][0-9]")), start=1):
            expected.append(
                PackagePartExpectation(part_no=part_no, filename=_safe_part_filename(path.name))
            )

    if not expected_full_sha and full_sha_path.exists():
        rows = parse_sha256sum_file(full_sha_path)
        if rows:
            expected_full_sha = rows[0][0]

    expected.sort(key=lambda item: item.part_no)
    return expected, expected_full_sha, source



def _part_suffix_number(path: Path) -> int | None:
    match = re.search(r"\.(\d{3})$", path.name)
    return int(match.group(1)) if match else None


def resolve_renamed_package_parts(
    parts_dir: Path,
    expected: list[PackagePartExpectation],
    *,
    canonical_dir: Path,
    skip_part_hash: bool = False,
) -> dict[str, Any]:
    """Resolve upload-renamed parts without trusting filenames alone.

    Chat clients may rename ``archive.zip.001`` to ``archive.zip(1).001``.
    A candidate is accepted only when the numeric suffix, expected size and
    expected SHA256 all match.  Canonical hard links (or copies as fallback)
    are created in a separate directory; source uploads are never renamed.
    """
    parts_dir = Path(parts_dir).expanduser().resolve()
    canonical_dir = Path(canonical_dir).expanduser().resolve()
    canonical_dir.mkdir(parents=True, exist_ok=True)
    resolved: list[dict[str, Any]] = []
    used: set[Path] = set()

    all_files = [path for path in parts_dir.iterdir() if path.is_file()]
    numbered_candidates = [path for path in all_files if _part_suffix_number(path) is not None]
    for part in expected:
        safe_filename = _safe_part_filename(part.filename)
        exact = parts_dir / safe_filename
        candidates = [exact] if exact.is_file() else []
        candidates.extend(
            path for path in numbered_candidates
            if path != exact and _part_suffix_number(path) == part.part_no
        )
        if not exact.is_file() and part.size_bytes is not None and part.sha256:
            candidates.extend(
                path for path in all_files
                if path != exact
                and path not in candidates
                and path.suffix.lower() in {".zip", f".{part.part_no:03d}"}
            )
        matches: list[tuple[Path, str | None]] = []
        rejected: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate in used:
                continue
            size = candidate.stat().st_size
            if part.size_bytes is not None and size != part.size_bytes:
                rejected.append({"path": str(candidate), "reason": "size_mismatch", "size_bytes": size})
                continue
            digest: str | None = None
            if part.sha256 and not skip_part_hash:
                digest = sha256_file(candidate)
                if digest != part.sha256:
                    rejected.append({"path": str(candidate), "reason": "sha256_mismatch", "sha256": digest})
                    continue
            matches.append((candidate, digest))
        if not matches:
            raise FileNotFoundError(
                f"Nie znaleziono poprawnej części {part.part_no:03d} ({part.filename}); "
                f"odrzucone={rejected}"
            )
        if len(matches) > 1:
            exact_matches = [item for item in matches if item[0] == exact]
            if len(exact_matches) == 1:
                matches = exact_matches
            else:
                raise ValueError(
                    f"Niejednoznaczne części dla numeru {part.part_no:03d}: "
                    + ", ".join(str(item[0]) for item in matches)
                )
        source, digest = matches[0]
        used.add(source)
        target = canonical_dir / safe_filename
        if target.exists():
            target.unlink()
        try:
            os.link(source, target)
            materialization = "hardlink"
        except OSError:
            shutil.copy2(source, target)
            materialization = "copy"
        resolved.append({
            "part_no": part.part_no,
            "expected_name": part.filename,
            "source_name": source.name,
            "source_path": str(source),
            "canonical_path": str(target),
            "renamed_by_host": source.name != part.filename,
            "materialization": materialization,
            "size_bytes": source.stat().st_size,
            "source_mtime_ns": source.stat().st_mtime_ns,
            "sha256": digest or part.sha256,
        })
    return {
        "ok": True,
        "parts_dir": str(parts_dir),
        "canonical_dir": str(canonical_dir),
        "parts_count": len(resolved),
        "renamed_parts_count": sum(1 for item in resolved if item["renamed_by_host"]),
        "resolved_parts": resolved,
    }


def verify_extracted_zip_tree(
    zip_path: Path,
    destination: Path,
    *,
    reject_extra_files: bool = False,
) -> dict[str, Any]:
    """Compare a completed extraction with the ZIP central directory."""
    zip_path = Path(zip_path).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    missing: list[str] = []
    wrong_size: list[dict[str, Any]] = []
    wrong_crc: list[dict[str, Any]] = []
    expected_files: set[str] = set()
    expected_dirs: set[str] = set()
    with zipfile.ZipFile(zip_path, "r") as zf:
        validate_zip_member_names(zf)
        for info in zf.infolist():
            rel = info.filename.rstrip("/")
            if not rel:
                continue
            target = destination / Path(*PurePosixPath(rel).parts)
            if info.is_dir():
                expected_dirs.add(rel)
                if not target.is_dir():
                    missing.append(info.filename)
            else:
                expected_files.add(rel)
                if not target.is_file():
                    missing.append(info.filename)
                elif target.stat().st_size != info.file_size:
                    wrong_size.append({
                        "path": info.filename,
                        "actual": target.stat().st_size,
                        "expected": info.file_size,
                    })
                else:
                    actual_crc = _crc32_file(target)
                    if actual_crc != info.CRC:
                        wrong_crc.append(
                            {
                                "path": info.filename,
                                "actual": f"{actual_crc:08x}",
                                "expected": f"{info.CRC:08x}",
                            }
                        )
    extra_files: list[str] = []
    if destination.exists():
        for path in destination.rglob("*"):
            if path.is_file():
                rel = path.relative_to(destination).as_posix()
                if rel not in expected_files:
                    extra_files.append(rel)
    ok = not missing and not wrong_size and not wrong_crc and (not reject_extra_files or not extra_files)
    return {
        "ok": ok,
        "zip_path": str(zip_path),
        "destination": str(destination),
        "expected_file_count": len(expected_files),
        "expected_directory_count": len(expected_dirs),
        "missing": missing,
        "wrong_size": wrong_size,
        "wrong_crc": wrong_crc,
        "extra_files": extra_files,
        "reject_extra_files": reject_extra_files,
    }


def verify_extracted_zip_set(
    zip_paths: list[Path],
    destination: Path,
    *,
    reject_extra_files: bool = False,
) -> dict[str, Any]:
    """Verify a set of independent ZIP volumes as one non-overlapping tree."""

    resolved = [Path(path).expanduser().resolve() for path in zip_paths]
    destination = Path(destination).expanduser().resolve()
    expected: dict[str, tuple[int, int]] = {}
    duplicate_members: list[str] = []
    for zip_path in resolved:
        with zipfile.ZipFile(zip_path, "r") as zf:
            validate_zip_member_names(zf)
            for info in zf.infolist():
                relative = info.filename.rstrip("/")
                if not relative or info.is_dir():
                    continue
                if relative in expected:
                    duplicate_members.append(relative)
                    continue
                expected[relative] = (int(info.file_size), int(info.CRC))
    if duplicate_members:
        raise ValueError(
            "Niezależne woluminy ZIP zawierają duplikaty wpisów: "
            + ", ".join(sorted(set(duplicate_members))[:20])
        )

    missing: list[str] = []
    wrong_size: list[dict[str, Any]] = []
    wrong_crc: list[dict[str, Any]] = []
    for relative, (expected_size, expected_crc) in expected.items():
        target = destination / Path(*PurePosixPath(relative).parts)
        if not target.is_file():
            missing.append(relative)
        elif target.stat().st_size != expected_size:
            wrong_size.append(
                {"path": relative, "actual": target.stat().st_size, "expected": expected_size}
            )
        else:
            actual_crc = _crc32_file(target)
            if actual_crc != expected_crc:
                wrong_crc.append(
                    {
                        "path": relative,
                        "actual": f"{actual_crc:08x}",
                        "expected": f"{expected_crc:08x}",
                    }
                )
    actual_files = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    } if destination.exists() else set()
    extra_files = sorted(actual_files - set(expected))
    ok = not missing and not wrong_size and not wrong_crc and (not reject_extra_files or not extra_files)
    return {
        "ok": ok,
        "archive_format": "independent",
        "zip_paths": [str(path) for path in resolved],
        "destination": str(destination),
        "expected_file_count": len(expected),
        "missing": missing,
        "wrong_size": wrong_size,
        "wrong_crc": wrong_crc,
        "extra_files": extra_files,
        "reject_extra_files": reject_extra_files,
    }


def extract_joined_zip_resumable(
    zip_path: Path,
    destination: Path,
    *,
    progress_path: Path | None = None,
    time_budget_seconds: float | None = None,
) -> dict[str, Any]:
    """Safely extract whole ZIP, resuming at completed file boundaries.

    Each file is written to ``.partial`` and atomically replaced.  The function
    stops only between members when a budget is reached, so no truncated file
    is ever marked complete.
    """
    zip_path = Path(zip_path).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    progress_path = Path(progress_path).expanduser().resolve() if progress_path else destination.parent / f".{destination.name}.extract-progress.json"
    destination.mkdir(parents=True, exist_ok=True)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    completed: dict[str, dict[str, Any]] = {}
    if progress_path.exists():
        try:
            raw = json.loads(progress_path.read_text(encoding="utf-8"))
            completed = dict(raw.get("completed") or {})
        except Exception:
            completed = {}
    started = time.monotonic()
    extracted_now = 0
    skipped_completed = 0

    def write_progress(*, state: str) -> None:
        payload = {
            "schema_version": "jazn_zip_extraction_progress/v1",
            "state": state,
            "zip_path": str(zip_path),
            "destination": str(destination),
            "completed": completed,
            "completed_count": len(completed),
            "updated_at_epoch": time.time(),
        }
        tmp = progress_path.with_suffix(progress_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, progress_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        validate_zip_member_names(zf)
        infos = zf.infolist()
        for info in infos:
            rel = info.filename.rstrip("/")
            if not rel:
                continue
            target = destination / Path(*PurePosixPath(rel).parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            record = completed.get(info.filename)
            if (
                record
                and target.is_file()
                and target.stat().st_size == info.file_size
                and int(record.get("crc32", -1)) == int(info.CRC)
                and _crc32_file(target) == int(info.CRC)
            ):
                skipped_completed += 1
                continue
            if time_budget_seconds is not None and extracted_now > 0 and (time.monotonic() - started) >= float(time_budget_seconds):
                write_progress(state="pending")
                return {
                    "ok": False,
                    "pending": True,
                    "zip_path": str(zip_path),
                    "destination": str(destination),
                    "progress_path": str(progress_path),
                    "completed_count": len(completed),
                    "total_members": len([item for item in infos if not item.is_dir()]),
                    "extracted_now": extracted_now,
                    "skipped_completed": skipped_completed,
                }
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".partial")
            partial.unlink(missing_ok=True)
            crc = 0
            size = 0
            try:
                with zf.open(info, "r") as source, partial.open("wb") as output:
                    while True:
                        chunk = source.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        size += len(chunk)
                        crc = zlib.crc32(chunk, crc)
                    output.flush()
                    os.fsync(output.fileno())
                crc &= 0xFFFFFFFF
                if size != info.file_size or crc != info.CRC:
                    raise ValueError(
                        f"Błąd integralności po rozpakowaniu {info.filename}: "
                        f"size={size}/{info.file_size}, crc={crc:08x}/{info.CRC:08x}"
                    )
                os.replace(partial, target)
                completed[info.filename] = {"size_bytes": size, "crc32": crc}
                extracted_now += 1
                write_progress(state="extracting")
            finally:
                partial.unlink(missing_ok=True)
    verification = verify_extracted_zip_tree(zip_path, destination, reject_extra_files=False)
    if not verification["ok"]:
        write_progress(state="verification_failed")
        raise ValueError(f"Rozpakowany filesystem nie odpowiada ZIP: {verification}")
    write_progress(state="complete")
    return {
        "ok": True,
        "pending": False,
        "zip_path": str(zip_path),
        "destination": str(destination),
        "progress_path": str(progress_path),
        "completed_count": len(completed),
        "extracted_now": extracted_now,
        "skipped_completed": skipped_completed,
        "verification": verification,
    }


def extract_independent_zip_set_resumable(
    zip_paths: list[Path],
    destination: Path,
    *,
    progress_path: Path | None = None,
    time_budget_seconds: float | None = None,
) -> dict[str, Any]:
    """Safely resume extraction of current independent package volumes."""

    resolved = [Path(path).expanduser().resolve() for path in zip_paths]
    destination = Path(destination).expanduser().resolve()
    progress_path = (
        Path(progress_path).expanduser().resolve()
        if progress_path
        else destination.parent / f".{destination.name}.extract-progress.json"
    )
    # Validate the complete member namespace before writing the first byte.
    verify_extracted_zip_set(resolved, destination, reject_extra_files=False)
    started = time.monotonic()
    volume_reports: list[dict[str, Any]] = []
    for index, zip_path in enumerate(resolved, start=1):
        remaining = None
        if time_budget_seconds is not None:
            remaining = max(0.0, float(time_budget_seconds) - (time.monotonic() - started))
        volume_progress = progress_path.with_name(
            f"{progress_path.stem}.volume-{index:03d}{progress_path.suffix}"
        )
        report = extract_joined_zip_resumable(
            zip_path,
            destination,
            progress_path=volume_progress,
            time_budget_seconds=remaining,
        )
        volume_reports.append(report)
        if report.get("pending"):
            return {
                "ok": False,
                "pending": True,
                "archive_format": "independent",
                "destination": str(destination),
                "completed_volumes": index - 1,
                "total_volumes": len(resolved),
                "volume_reports": volume_reports,
            }
    verification = verify_extracted_zip_set(resolved, destination, reject_extra_files=False)
    if not verification.get("ok"):
        raise ValueError(f"Rozpakowany filesystem nie odpowiada zestawowi ZIP: {verification}")
    return {
        "ok": True,
        "pending": False,
        "archive_format": "independent",
        "destination": str(destination),
        "completed_volumes": len(resolved),
        "total_volumes": len(resolved),
        "volume_reports": volume_reports,
        "verification": verification,
    }

def validate_package_parts(
    parts_dir: Path,
    base_zip_name: str,
    *,
    skip_part_hash: bool = False,
) -> tuple[list[PackagePartExpectation], str | None, str]:
    parts_dir = Path(parts_dir).expanduser().resolve()
    base_zip_name = sanitize_zip_name(base_zip_name)

    expected, expected_full_sha, source = load_package_expectations(parts_dir, base_zip_name)

    if not expected:
        raise FileNotFoundError(f"Brak części paczki: {base_zip_name}.001, {base_zip_name}.002, ...")

    expected_names = {part.filename for part in expected}
    extra_parts = sorted(
        path.name
        for path in parts_dir.glob(f"{base_zip_name}.[0-9][0-9][0-9]")
        if path.name not in expected_names
    )
    if extra_parts:
        raise ValueError("Znaleziono dodatkowe części nieujęte w manifeście/hashach: " + ", ".join(extra_parts))

    for index, part in enumerate(expected, start=1):
        suffix = f".{index:03d}"
        if not part.filename.endswith(suffix):
            raise ValueError(f"Nieciągła albo błędna kolejność części: oczekiwano {suffix}, jest {part.filename}")

        part_path = parts_dir / part.filename
        if not part_path.exists() or not part_path.is_file():
            raise FileNotFoundError(f"Brak części: {part.filename}")

        if part.size_bytes is not None and part_path.stat().st_size != part.size_bytes:
            raise ValueError(
                f"Zły rozmiar części {part.filename}: "
                f"jest {part_path.stat().st_size}, oczekiwano {part.size_bytes}"
            )

        if part.sha256 and not skip_part_hash:
            actual = sha256_file(part_path)
            if actual != part.sha256:
                raise ValueError(f"Zły SHA256 części {part.filename}: {actual}, oczekiwano {part.sha256}")

    return expected, expected_full_sha, source


def join_split_package_to_zip(
    parts_dir: Path,
    base_zip_name: str,
    *,
    zip_out: Path | None = None,
    skip_part_hash: bool = False,
    force: bool = False,
    keep_existing: bool = False,
) -> Path:
    parts_dir = Path(parts_dir).expanduser().resolve()
    base_zip_name = sanitize_zip_name(base_zip_name)
    out_zip = Path(zip_out).expanduser().resolve() if zip_out is not None else parts_dir / base_zip_name

    expected, expected_full_sha, _source = validate_package_parts(
        parts_dir,
        base_zip_name,
        skip_part_hash=skip_part_hash,
    )

    if out_zip.exists():
        if keep_existing:
            pass
        elif not force:
            raise FileExistsError(f"Pełny ZIP już istnieje: {out_zip}. Użyj force=True albo usuń plik.")
        else:
            out_zip.unlink()

    if not out_zip.exists():
        tmp = out_zip.with_name(out_zip.name + ".joining.tmp")
        if tmp.exists():
            tmp.unlink()

        try:
            with tmp.open("xb") as target:
                for part in expected:
                    with (parts_dir / part.filename).open("rb") as source:
                        shutil.copyfileobj(source, target, length=CHUNK_SIZE)
            os.replace(tmp, out_zip)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    if expected_full_sha:
        actual = sha256_file(out_zip)
        if actual != expected_full_sha:
            raise ValueError(f"Zły SHA256 pełnego ZIP-a: {actual}, oczekiwano {expected_full_sha}")

    return out_zip


def unsafe_zip_member_name(name: str) -> str | None:
    normalized = str(name).replace("\\", "/")
    path = PurePosixPath(normalized)

    if "\\" in name:
        return "backslash separator"
    if name.startswith(("/", "\\")):
        return "absolute path"
    if len(name) >= 2 and name[1] == ":":
        return "drive path"
    if any(part == ".." for part in path.parts):
        return "parent traversal"
    if "\x00" in name:
        return "NUL byte"

    return None


def validate_zip_member_names(zf: zipfile.ZipFile) -> None:
    validate_zip_resources(zf)
    bad: list[str] = []
    seen: set[str] = set()
    files: set[str] = set()
    directories: set[str] = set()
    for info in zf.infolist():
        reason = unsafe_zip_member_name(info.filename)
        if reason:
            bad.append(f"{info.filename!r}: {reason}")
            continue
        relative = info.filename.rstrip("/")
        if relative in seen:
            bad.append(f"{info.filename!r}: duplicate entry")
            continue
        seen.add(relative)
        unix_type = (int(info.external_attr) >> 16) & 0o170000
        if unix_type == stat.S_IFLNK:
            bad.append(f"{info.filename!r}: symbolic link")
            continue
        if info.is_dir():
            directories.add(relative)
        else:
            files.add(relative)

    for file_name in sorted(files):
        if file_name in directories:
            bad.append(f"{file_name!r}: file-directory collision")
        parts = PurePosixPath(file_name).parts
        for index in range(1, len(parts)):
            parent = PurePosixPath(*parts[:index]).as_posix()
            if parent in files:
                bad.append(f"{file_name!r}: parent path is a file ({parent!r})")
                break

    if bad:
        sample = "\n".join(bad[:20])
        more = "" if len(bad) <= 20 else f"\n... oraz {len(bad) - 20} więcej"
        raise ValueError("ZIP zawiera niebezpieczne ścieżki:\n" + sample + more)


def test_joined_zip(out_zip: Path, *, run_crc: bool = True) -> dict[str, Any]:
    out_zip = Path(out_zip).expanduser().resolve()

    if not out_zip.exists() or not out_zip.is_file():
        raise FileNotFoundError(f"Nie znaleziono pełnego ZIP-a: {out_zip}")

    with zipfile.ZipFile(out_zip, "r") as zf:
        infos = zf.infolist()
        validate_zip_member_names(zf)

        if run_crc:
            bad = zf.testzip()
            if bad:
                raise ValueError(f"Błędny CRC/header wpisu ZIP: {bad}")

    return {
        "ok": True,
        "zip_path": str(out_zip),
        "entries": len(infos),
        "size_bytes": out_zip.stat().st_size,
        "crc_tested": bool(run_crc),
    }


def test_split_package(
    parts_dir: Path,
    base_zip_name: str,
    *,
    zip_out: Path | None = None,
    skip_part_hash: bool = False,
    join_if_missing: bool = True,
    force_join: bool = False,
    run_crc: bool = True,
) -> dict[str, Any]:
    parts_dir = Path(parts_dir).expanduser().resolve()
    base_zip_name = sanitize_zip_name(base_zip_name)
    out_zip = Path(zip_out).expanduser().resolve() if zip_out is not None else parts_dir / base_zip_name

    expected, expected_full_sha, source = validate_package_parts(
        parts_dir,
        base_zip_name,
        skip_part_hash=skip_part_hash,
    )

    if not out_zip.exists():
        if not join_if_missing:
            raise FileNotFoundError(f"Pełny ZIP nie istnieje: {out_zip}")
        out_zip = join_split_package_to_zip(
            parts_dir,
            base_zip_name,
            zip_out=out_zip,
            skip_part_hash=skip_part_hash,
            force=force_join,
        )
    elif expected_full_sha:
        actual = sha256_file(out_zip)
        if actual != expected_full_sha:
            if not force_join:
                raise ValueError(f"Istniejący pełny ZIP ma zły SHA256: {actual}, oczekiwano {expected_full_sha}")
            out_zip = join_split_package_to_zip(
                parts_dir,
                base_zip_name,
                zip_out=out_zip,
                skip_part_hash=skip_part_hash,
                force=True,
            )

    zip_report = test_joined_zip(out_zip, run_crc=run_crc)

    return {
        "ok": True,
        "parts_dir": str(parts_dir),
        "base_zip_name": base_zip_name,
        "parts_count": len(expected),
        "parts_source": source,
        "expected_full_sha256": expected_full_sha,
        **zip_report,
    }

# Public helpers with test-like names. Prevent pytest from collecting them when
# imported into test modules.
setattr(test_joined_zip, "__test__", False)
setattr(test_split_package, "__test__", False)

def _build_cli_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate, join and test split Jaźń ZIP packages."
    )
    parser.add_argument("--parts-dir", default=".", help="Folder z częściami .zip.001, .zip.002 itd.")
    parser.add_argument("--zip-name", default="", help="Nazwa bazowa pełnego ZIP-a, np. jazn_latka_vX.zip.")
    parser.add_argument("--zip-out", default="", help="Ścieżka wyjściowa pełnego ZIP-a.")
    parser.add_argument("--skip-part-hash", action="store_true", help="Nie sprawdzaj SHA256 pojedynczych części.")
    parser.add_argument("--skip-crc", action="store_true", help="Nie uruchamiaj zipfile.testzip().")
    parser.add_argument("--force-join", action="store_true", help="Nadpisz istniejący pełny ZIP, jeśli trzeba.")
    parser.add_argument("--keep-existing", action="store_true", help="Użyj istniejącego pełnego ZIP-a bez ponownego sklejania.")
    parser.add_argument("--join-package", action="store_true", help="Sklej części w pełny ZIP.")
    parser.add_argument("--test-package", action="store_true", help="Zweryfikuj części, pełny ZIP i CRC.")
    add_progress_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    parts_dir = Path(args.parts_dir).expanduser().resolve()
    base_zip_name = infer_base_zip_name(parts_dir, args.zip_name or None)
    zip_out = Path(args.zip_out).expanduser().resolve() if args.zip_out else parts_dir / base_zip_name

    if not args.join_package and not args.test_package:
        parser.error("Podaj --join-package albo --test-package.")

    if args.join_package:
        display = TerminalProgress.from_namespace(args, "split-zip-join", style="spinner")
        display.start_spinner("Sklejam części i obliczam SHA-256 pełnego ZIP-a", symbol="folder")
        try:
            out_zip = join_split_package_to_zip(
                parts_dir,
                base_zip_name,
                zip_out=zip_out,
                skip_part_hash=args.skip_part_hash,
                force=args.force_join,
                keep_existing=args.keep_existing,
            )
            digest = sha256_file(out_zip)
        except Exception as exc:
            display.fail(f"Sklejanie paczki przerwane: {type(exc).__name__}")
            raise
        display.finish(True, "Pełny ZIP został złożony")
        print(json.dumps(
            {
                "ok": True,
                "action": "join-package",
                "zip_path": str(out_zip),
                "sha256": digest,
            },
            ensure_ascii=False,
            indent=2,
        ))

    if args.test_package:
        display = TerminalProgress.from_namespace(args, "split-zip-test", style="spinner")
        display.start_spinner("Weryfikuję części, SHA-256, strukturę i CRC ZIP", symbol="lock")
        try:
            report = test_split_package(
                parts_dir,
                base_zip_name,
                zip_out=zip_out,
                skip_part_hash=args.skip_part_hash,
                join_if_missing=True,
                force_join=args.force_join,
                run_crc=not args.skip_crc,
            )
        except Exception as exc:
            display.fail(f"Weryfikacja paczki przerwana: {type(exc).__name__}")
            raise
        display.finish(bool(report.get("ok")), "Weryfikacja paczki zakończona")
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
