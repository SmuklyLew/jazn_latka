from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Event
from typing import Any, Callable
import uuid

from .archive import create_zip, safe_extract_zip, sha256_file, verify_zip
from .constants import GENERATOR_TITLE, GENERATOR_VERSION
from .errors import PackCancelled, PackIntegrityError, PackSafetyError, PackValidationError
from .manifest import build_manifest, write_manifest
from .models import ContentMode, PackPlan, PackRequest, PackResult, ProgressEvent, TransportMode
from .scanner import build_pack_plan
from .settings import settings_path
from .transport import join_parts, split_archive, verify_parts

ProgressCallback = Callable[[ProgressEvent], None]


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_output_boundary(plan: PackPlan) -> None:
    output = plan.request.output_root
    source = plan.request.source_root
    if output == source or _is_within(output, source):
        raise PackSafetyError("Folder wynikowy nie może znajdować się wewnątrz folderu Jaźni.")
    if plan.request.memory_root is not None:
        memory = plan.request.memory_root
        if output == memory or _is_within(output, memory):
            raise PackSafetyError("Folder wynikowy nie może znajdować się wewnątrz pamięci Jaźni.")


def disk_preflight(plan: PackPlan) -> dict[str, int]:
    output = plan.request.output_root
    output.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(output)
    overhead = max(64 * 1024 * 1024, plan.file_count * 512)
    max_archive = plan.source_total_size_bytes + overhead
    required = max_archive * (2 if plan.request.transport is TransportMode.SPLIT else 1)
    required += 64 * 1024 * 1024
    if usage.free < required:
        raise PackValidationError(
            "Za mało wolnego miejsca na bezpieczne utworzenie paczki: "
            f"wymagane~{required} B, wolne={usage.free} B."
        )
    return {"free_bytes": usage.free, "required_bytes": required}


def plan_pack(request: PackRequest) -> PackPlan:
    plan = build_pack_plan(request)
    validate_output_boundary(plan)
    return plan


def pack(
    request: PackRequest,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> PackResult:
    plan = plan_pack(request)
    disk_preflight(plan)
    output_root = plan.request.output_root
    final_name = plan.package_basename[:-4]
    final_dir = output_root / final_name

    staging = Path(tempfile.mkdtemp(prefix=".jazn-pack-staging-", dir=str(output_root)))
    backup: Path | None = None
    committed = False
    try:
        archive = staging / plan.package_basename
        create_zip(plan, archive, callback=callback, cancel_event=cancel_event)
        logical_size = archive.stat().st_size

        parts: tuple[Path, ...] = ()
        parts_sha: Path | None = None
        join_script: Path | None = None
        if plan.request.transport is TransportMode.SPLIT:
            logical_sha, parts, parts_sha, join_script = split_archive(
                archive,
                part_size_bytes=plan.request.part_size_mib * 1024 * 1024,
                force=plan.request.force_split,
                callback=callback,
                cancel_event=cancel_event,
            )
            split_enabled = bool(parts)
            logical_archive: Path | None = None if split_enabled else archive
        else:
            logical_sha = sha256_file(archive, callback=callback, cancel_event=cancel_event)
            split_enabled = False
            logical_archive = archive

        sha_path = staging / f"{plan.package_basename}.sha256"
        sha_path.write_text(f"{logical_sha}  {plan.package_basename}\n", encoding="utf-8")

        part_items: list[dict[str, Any]] = []
        if parts:
            for part in parts:
                part_items.append(
                    {
                        "filename": part.name,
                        "size_bytes": part.stat().st_size,
                        "sha256": sha256_file(part, cancel_event=cancel_event),
                    }
                )
            verify_parts(parts[0], callback=callback, cancel_event=cancel_event)

        verification = {
            "ok": True,
            "zip_crc": "ok",
            "logical_sha256": logical_sha,
            "parts_sha256": "ok" if parts else "not_applicable",
        }
        manifest_path = staging / f"{plan.package_basename}.package.json"
        manifest = build_manifest(
            plan,
            logical_filename=plan.package_basename,
            logical_sha256=logical_sha,
            logical_size_bytes=logical_size,
            split_enabled=split_enabled,
            parts=part_items,
            verification=verification,
        )
        write_manifest(manifest_path, manifest)

        if final_dir.exists():
            if not plan.request.overwrite:
                raise PackSafetyError(
                    f"Wynik już istnieje: {final_dir}. Włącz overwrite, aby zastąpić."
                )
            backup = output_root / f".{final_name}.backup-{uuid.uuid4().hex}"
            os.replace(final_dir, backup)

        os.replace(staging, final_dir)
        committed = True
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
            backup = None

        result_parts = tuple(final_dir / item.name for item in parts)
        final_archive = final_dir / archive.name if logical_archive is not None else None
        return PackResult(
            ok=True,
            output_root=final_dir,
            logical_archive=final_archive,
            manifest_path=final_dir / manifest_path.name,
            sha256_path=final_dir / sha_path.name,
            logical_sha256=logical_sha,
            logical_size_bytes=logical_size,
            parts=result_parts,
            parts_sha256_path=(final_dir / parts_sha.name) if parts_sha else None,
            join_script_path=(final_dir / join_script.name) if join_script else None,
        )
    except Exception:
        if backup is not None and not final_dir.exists():
            os.replace(backup, final_dir)
            backup = None
        raise
    finally:
        if not committed and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def verify_package(
    path: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> dict[str, Any]:
    source = path.expanduser().resolve()
    if source.name.lower().endswith(".zip.001"):
        parts_report = verify_parts(source, callback=callback, cancel_event=cancel_event)
        temp_dir = Path(tempfile.mkdtemp(prefix=".jazn-pack-verify-"))
        try:
            joined = join_parts(
                source,
                temp_dir / str(parts_report["logical_filename"]),
                callback=callback,
                cancel_event=cancel_event,
            )
            zip_report = verify_zip(joined, callback=callback, cancel_event=cancel_event)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return {"ok": True, "kind": "split", "parts": parts_report, "zip": zip_report}
    if source.suffix.lower() == ".zip":
        return {"ok": True, "kind": "zip", "zip": verify_zip(source, callback=callback, cancel_event=cancel_event)}
    raise PackValidationError("Obsługiwane są paczki *.zip oraz pierwsze części *.zip.001.")


def unpack_package(
    path: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> Path:
    source = path.expanduser().resolve()
    if source.name.lower().endswith(".zip.001"):
        temp_dir = Path(tempfile.mkdtemp(prefix=".jazn-pack-join-"))
        try:
            joined = join_parts(source, temp_dir / source.name[:-4], callback=callback, cancel_event=cancel_event)
            return safe_extract_zip(
                joined,
                destination.expanduser().resolve(),
                overwrite=overwrite,
                callback=callback,
                cancel_event=cancel_event,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    if source.suffix.lower() == ".zip":
        return safe_extract_zip(
            source,
            destination.expanduser().resolve(),
            overwrite=overwrite,
            callback=callback,
            cancel_event=cancel_event,
        )
    raise PackValidationError("Obsługiwane są paczki *.zip oraz pierwsze części *.zip.001.")


def config_report() -> dict[str, Any]:
    tkinter_ok = False
    tkinter_error: str | None = None
    try:
        import tkinter  # noqa: F401
        tkinter_ok = True
    except Exception as exc:  # Import/runtime availability report, not an execution fallback.
        tkinter_error = f"{type(exc).__name__}: {exc}"
    return {
        "ok": True,
        "generator_version": GENERATOR_VERSION,
        "generator_title": GENERATOR_TITLE,
        "python": sys.version,
        "platform": sys.platform,
        "settings_path": str(settings_path()),
        "features": {
            "zip": True,
            "zip64": True,
            "split_transport": True,
            "sha256": True,
            "crc": True,
            "safe_extract": True,
            "text_ui": True,
            "terminal_tui": True,
            "studio_gui": tkinter_ok,
        },
        "tkinter_error": tkinter_error,
        "scope": "archive-system-memory-system+memory",
        "not_in_scope": ["dependency-bundle", "wheelhouse", "python-runtime", "target-platform"],
    }
