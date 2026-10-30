"""Bounded, primitive JSON layout; never unpickle Qt state or private data."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .core import _path_without_links
from latka_jazn.core.runtime_root import workspace_runtime_path

SCHEMA = "jazn_heart_layout/v3"


def layout_path(root: Path) -> Path:
    return _path_without_links(workspace_runtime_path(root) / "jazn_run_studio" / "layout.json")


def validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema") not in (SCHEMA, "jazn_heart_layout/v2", "jazn_heart_layout/v1"):
        raise ValueError("Nieznana wersja układu")
    allowed = {"schema", "width", "height", "sidebar_right", "sidebar_visible", "dock_visible", "dock_area", "setup_scope",
               "shell_sizes", "content_sizes", "active_section", "open_sections", "operator_tab", "dock_height"}
    if set(data) - allowed:
        raise ValueError("Nieznane pola układu")
    for name, low, high in (("width", 860, 7680), ("height", 580, 4320), ("dock_area", 0, 3), ("operator_tab", 0, 5), ("dock_height", 180, 3000)):
        if name in data and (type(data[name]) is not int or not low <= data[name] <= high):
            raise ValueError("Nieprawidłowy rozmiar lub obszar panelu")
    for name in ("sidebar_right", "sidebar_visible", "dock_visible"):
        if name in data and type(data[name]) is not bool:
            raise ValueError("Nieprawidłowa widoczność panelu")
    scope = data.get("setup_scope", "")
    if not isinstance(scope, str) or (scope and (len(scope) != 64 or any(c not in "0123456789abcdef" for c in scope))):
        raise ValueError("Nieprawidłowy zakres kreatora")
    for key in ("shell_sizes", "content_sizes"):
        if key in data and (not isinstance(data[key], list) or len(data[key]) != 2
                            or any(type(v) is not int or not 0 <= v <= 12000 for v in data[key])):
            raise ValueError("Nieprawidłowe wymiary podziału")
    sections = data.get("open_sections", [])
    if (not isinstance(sections, list) or len(sections) > 24
            or any(not isinstance(v, str) or not 0 < len(v) <= 80 or any(ord(c) < 32 for c in v) for v in sections)):
        raise ValueError("Nieprawidłowe sekcje układu")
    active = data.get("active_section", "Pulpit")
    if not isinstance(active, str) or not 0 < len(active) <= 80 or any(ord(c) < 32 for c in active):
        raise ValueError("Nieprawidłowa aktywna sekcja")
    return {**data, "schema": SCHEMA}


def load_layout(root: Path) -> dict[str, Any]:
    path = layout_path(root)
    if not path.exists():
        return {"schema": SCHEMA}
    if not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("Zbyt duży lub nieprawidłowy plik układu")
    return validate(json.loads(path.read_bytes()))


def save_layout(root: Path, data: dict[str, Any]) -> None:
    payload = (json.dumps(validate(data), ensure_ascii=False, indent=2) + "\n").encode()
    target = layout_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=".layout-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
