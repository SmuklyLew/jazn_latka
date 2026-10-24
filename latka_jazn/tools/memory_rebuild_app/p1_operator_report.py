"""Read-only operator adapter for the existing P1 services; codes-only output."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .models import RebuildProject
from .p1_active_memory_readiness import assess_active_memory_readiness
from .p1_memory_inspection import inspect_memory_layout
from .p1_memory_provenance import _unsafe_path, compare_memory_provenance
from .p1_provenance_chain import PinnedMemoryArtifact, _same_source_stamp, _stamp

MAX_PROJECT_BYTES = 2 * 1024 * 1024
OPERATIONS = frozenset({"layout", "comparison", "readiness"})


def _read_project(path: Path) -> RebuildProject:
    # Do not instantiate ProjectStore: even its constructor creates directories.
    if _unsafe_path(path) or not path.is_file():
        raise ValueError("project_file_unavailable")
    before = path.stat()
    if before.st_size > MAX_PROJECT_BYTES:
        raise ValueError("project_size_limit")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if _stamp(opened) != _stamp(before):
            raise ValueError("project_changed")
        raw = stream.read(MAX_PROJECT_BYTES + 1)
        if not _same_source_stamp(opened, os.fstat(stream.fileno())):
            raise ValueError("project_changed")
    if len(raw) > MAX_PROJECT_BYTES or not _same_source_stamp(before, path.stat()) or _unsafe_path(path):
        raise ValueError("project_changed")
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict) or not data.get("target_root"):
        raise ValueError("project_shape_invalid")
    # Preserve evidence of links before the canonical model resolves paths.
    paths = [data["target_root"], data.get("source_directory")]
    for collection in ("sources", "baselines"):
        items = data.get(collection, [])
        if not isinstance(items, list) or len(items) > 10000:
            raise ValueError("project_inventory_limit")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("project_shape_invalid")
            paths.append(item.get("path"))
    for value in paths:
        if value and (not isinstance(value, str) or _unsafe_path(Path(value).expanduser())):
            raise ValueError("project_path_unsafe")
    return RebuildProject.from_dict(data)


def build_operator_report(
    root: Path, *, operation: str, project_file: Path | None = None,
    reference: Path | None = None, reference_sha256: str | None = None,
    parent: Path | None = None, parent_sha256: str | None = None,
) -> dict[str, Any]:
    """Complete an observation, never infer recall or authorize activation."""
    report: dict[str, Any] = {
        "schema": "jazn_memory_operator_observation/v1", "operation": operation if operation in OPERATIONS else "unknown",
        "ok": False, "read_only": True, "memory_modified": False,
        "activation_preflight_passed": False, "activation_authorized": False,
    }
    try:
        if operation not in OPERATIONS:
            raise ValueError("unknown_operation")
        if operation == "readiness":
            if bool(reference) != bool(reference_sha256) or bool(parent) != bool(parent_sha256):
                raise ValueError("incomplete_reference_pin")
            if parent is not None and reference is None:
                raise ValueError("parent_without_reference")
            if any(value and re.fullmatch(r"[0-9a-fA-F]{64}", value) is None
                   for value in (reference_sha256, parent_sha256)):
                raise ValueError("invalid_reference_digest")
            result = assess_active_memory_readiness(root,
                pinned_reference=PinnedMemoryArtifact(reference, reference_sha256 or "") if reference else None,
                pinned_parent=PinnedMemoryArtifact(parent, parent_sha256 or "") if parent else None)
        else:
            if any((reference, reference_sha256, parent, parent_sha256)):
                raise ValueError("pins_require_runtime_observation")
            if project_file is None:
                raise ValueError("project_required")
            project = _read_project(project_file.expanduser())
            if operation == "layout":
                result = inspect_memory_layout(project, system_root=root)
            else:
                result = compare_memory_provenance(project, system_root=root)
        return {**report, "ok": True, "result": result}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError):
        # Never return arbitrary parser/OS/SQLite messages containing user paths.
        return {**report, "state": "blocked", "issue": "observation_input_or_read_failed"}
