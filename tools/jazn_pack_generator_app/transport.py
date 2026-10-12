from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Event
from typing import Callable

from .errors import PackCancelled, PackIntegrityError, PackValidationError
from .models import ProgressEvent

ProgressCallback = Callable[[ProgressEvent], None]


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise PackCancelled("Operacja została anulowana.")


def _emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    if callback is not None:
        callback(event)


def split_archive(
    archive: Path,
    *,
    part_size_bytes: int,
    force: bool = False,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> tuple[str, tuple[Path, ...], Path | None, Path | None]:
    if part_size_bytes <= 0:
        raise PackValidationError("Rozmiar części musi być większy od zera.")
    size = archive.stat().st_size
    if size <= part_size_bytes and not force:
        logical_sha = _sha256(archive, callback=callback, cancel_event=cancel_event)
        return logical_sha, (), None, None

    logical = hashlib.sha256()
    parts: list[Path] = []
    processed = 0
    with archive.open("rb") as source:
        index = 1
        while True:
            _check_cancel(cancel_event)
            chunk = source.read(part_size_bytes)
            if not chunk:
                break
            logical.update(chunk)
            part = archive.with_name(f"{archive.name}.{index:03d}")
            part.write_bytes(chunk)
            parts.append(part)
            processed += len(chunk)
            _emit(callback, ProgressEvent("split", "Dzielenie paczki", processed, size, part.name))
            index += 1

    if not parts:
        raise PackIntegrityError(f"Nie utworzono żadnej części: {archive}")

    parts_sha = archive.with_name(archive.name + ".parts.sha256")
    lines = [
        f"logical_sha256  {logical.hexdigest()}",
        f"logical_filename  {archive.name}",
        f"part_size_bytes  {part_size_bytes}",
    ]
    for part in parts:
        lines.append(f"{_sha256(part)}  {part.name}")
    parts_sha.write_text("\n".join(lines) + "\n", encoding="utf-8")

    join_script = archive.with_name(archive.name + ".join.ps1")
    join_script.write_text(_powershell_join_script(archive.name), encoding="utf-8")
    archive.unlink()
    return logical.hexdigest(), tuple(parts), parts_sha, join_script


def _sha256(
    path: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    current = 0
    with path.open("rb") as handle:
        while True:
            _check_cancel(cancel_event)
            chunk = handle.read(4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            current += len(chunk)
            _emit(callback, ProgressEvent("hash", "Obliczanie SHA-256", current, total, path.name))
    return digest.hexdigest()


def discover_parts(first_part: Path) -> tuple[Path, tuple[Path, ...]]:
    name = first_part.name
    if not name.lower().endswith(".zip.001"):
        raise PackValidationError("Rozpocznij od pierwszej części *.zip.001.")
    base = first_part.with_name(name[:-4])
    parts: list[Path] = []
    index = 1
    while True:
        candidate = base.with_name(f"{base.name}.{index:03d}")
        if not candidate.is_file():
            break
        parts.append(candidate)
        index += 1
    if not parts:
        raise PackValidationError(f"Nie znaleziono części dla {first_part}")
    return base, tuple(parts)


def join_parts(
    first_part: Path,
    destination: Path | None = None,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> Path:
    base, parts = discover_parts(first_part.resolve())
    target = destination.resolve() if destination else base.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".join.tmp")
    total = sum(item.stat().st_size for item in parts)
    current = 0
    digest = hashlib.sha256()
    try:
        with temp.open("wb") as output:
            for part in parts:
                with part.open("rb") as source:
                    while True:
                        _check_cancel(cancel_event)
                        chunk = source.read(4 * 1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        output.write(chunk)
                        current += len(chunk)
                        _emit(callback, ProgressEvent("join", "Łączenie części", current, total, part.name))

        sidecar = base.with_name(base.name + ".parts.sha256")
        if sidecar.is_file():
            expected: str | None = None
            for line in sidecar.read_text(encoding="utf-8-sig").splitlines():
                fields = line.split()
                if len(fields) >= 2 and fields[0] == "logical_sha256":
                    expected = fields[1].strip().lower()
                    break
            if expected and digest.hexdigest().lower() != expected:
                raise PackIntegrityError("SHA-256 złączonego ZIP-a nie zgadza się z sidecarem.")
        temp.replace(target)
        return target
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def verify_parts(
    first_part: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> dict[str, object]:
    base, parts = discover_parts(first_part.resolve())
    sidecar = base.with_name(base.name + ".parts.sha256")
    if not sidecar.is_file():
        raise PackIntegrityError(f"Brak pliku kontrolnego części: {sidecar}")
    expected_parts: dict[str, str] = {}
    logical_expected: str | None = None
    for line in sidecar.read_text(encoding="utf-8-sig").splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        if fields[0] == "logical_sha256":
            logical_expected = fields[1].lower()
        elif len(fields[0]) == 64:
            expected_parts[fields[1]] = fields[0].lower()

    logical = hashlib.sha256()
    for index, part in enumerate(parts, start=1):
        _check_cancel(cancel_event)
        digest = hashlib.sha256()
        with part.open("rb") as handle:
            while True:
                chunk = handle.read(4 * 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                logical.update(chunk)
        observed = digest.hexdigest().lower()
        expected = expected_parts.get(part.name)
        if expected is None:
            raise PackIntegrityError(f"Brak SHA-256 dla części {part.name}")
        if observed != expected:
            raise PackIntegrityError(f"SHA-256 części nie zgadza się: {part.name}")
        _emit(callback, ProgressEvent("verify_parts", "Sprawdzanie części", index, len(parts), part.name))

    if logical_expected and logical.hexdigest().lower() != logical_expected:
        raise PackIntegrityError("SHA-256 logicznego ZIP-a nie zgadza się po złożeniu części.")
    return {
        "ok": True,
        "logical_filename": base.name,
        "logical_sha256": logical.hexdigest(),
        "part_count": len(parts),
        "parts": [part.name for part in parts],
    }


def _powershell_join_script(logical_filename: str) -> str:
    template = '''param(
    [string]$Output = "{logical_filename}"
)
$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$first = Join-Path $base "{logical_filename}.001"
if (-not (Test-Path -LiteralPath $first)) {{
    throw "Brak pierwszej części: $first"
}}
$outPath = Join-Path $base $Output
$tmpPath = "$outPath.join.tmp"
if (Test-Path -LiteralPath $tmpPath) {{ Remove-Item -LiteralPath $tmpPath -Force }}
$stream = [System.IO.File]::Open($tmpPath, [System.IO.FileMode]::CreateNew)
try {{
    $i = 1
    while ($true) {{
        $part = Join-Path $base ("{logical_filename}." + $i.ToString("000"))
        if (-not (Test-Path -LiteralPath $part)) {{ break }}
        $input = [System.IO.File]::OpenRead($part)
        try {{ $input.CopyTo($stream) }} finally {{ $input.Dispose() }}
        $i++
    }}
}} finally {{
    $stream.Dispose()
}}
Move-Item -LiteralPath $tmpPath -Destination $outPath -Force
Write-Host "Połączono do: $outPath"
'''
    return template.format(logical_filename=logical_filename)
