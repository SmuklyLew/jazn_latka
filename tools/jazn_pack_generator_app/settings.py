from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_COMPRESSION_LEVEL,
    DEFAULT_PART_SIZE_MIB,
    DEFAULT_UI_MODE,
    GENERATOR_VERSION,
    SETTINGS_FILENAME,
    SETTINGS_SCHEMA,
    UI_MODE_CHOICES,
)
from .errors import PackValidationError


def settings_path() -> Path:
    explicit = str(os.environ.get("JAZN_PACK_GENERATOR_SETTINGS") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().with_name(SETTINGS_FILENAME)


def default_settings() -> dict[str, Any]:
    return {
        "schema_version": SETTINGS_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "ui_mode": DEFAULT_UI_MODE,
        "source_root": "",
        "memory_root": "",
        "output_root": "",
        "part_size_mib": DEFAULT_PART_SIZE_MIB,
        "compression_level": DEFAULT_COMPRESSION_LEVEL,
        "remember_last_paths": True,
    }


def _normalized(payload: dict[str, Any]) -> dict[str, Any]:
    result = default_settings()
    result.update({key: value for key, value in payload.items() if key in result})
    result["schema_version"] = SETTINGS_SCHEMA
    result["generator_version"] = GENERATOR_VERSION
    if str(result["ui_mode"]) not in UI_MODE_CHOICES:
        result["ui_mode"] = DEFAULT_UI_MODE
    result["part_size_mib"] = max(1, int(result["part_size_mib"]))
    result["compression_level"] = min(9, max(0, int(result["compression_level"])))
    result["remember_last_paths"] = bool(result["remember_last_paths"])
    return result


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return default_settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default_settings()
    return _normalized(raw if isinstance(raw, dict) else {})


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalized(payload)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        temp.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise PackValidationError(f"Nie można zapisać ustawień: {path}: {exc}") from exc
    return normalized
