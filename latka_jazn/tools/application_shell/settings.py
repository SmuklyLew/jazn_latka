from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ShellSettings:
    ui_mode: str = "window"
    splash_enabled: bool = True
    diagnostics_enabled: bool = True
    diagnostics_limit: int = 500
    log_level: str = "INFO"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any], *, defaults: "ShellSettings | None" = None) -> "ShellSettings":
        return _normalized(payload, defaults)


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "tak"}:
            return True
        if normalized in {"0", "false", "no", "off", "nie"}:
            return False
    return fallback


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return fallback


def _normalized(payload: dict[str, Any], defaults: ShellSettings | None = None) -> ShellSettings:
    fallback = defaults or ShellSettings()
    base = asdict(fallback)
    for key in tuple(base):
        if key in payload:
            base[key] = payload[key]

    mode = str(base["ui_mode"] or fallback.ui_mode).strip().lower()
    if mode == "studio":
        mode = "window"
    if mode not in {"text", "tui", "window"}:
        mode = fallback.ui_mode if fallback.ui_mode in {"text", "tui", "window"} else "window"

    level = str(base["log_level"] or fallback.log_level).strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        fallback_level = str(fallback.log_level or "INFO").upper()
        level = fallback_level if fallback_level in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO"

    diagnostics_limit = _coerce_int(base["diagnostics_limit"], fallback.diagnostics_limit)
    diagnostics_limit = max(50, min(5000, diagnostics_limit))

    return ShellSettings(
        ui_mode=mode,
        splash_enabled=_coerce_bool(base["splash_enabled"], fallback.splash_enabled),
        diagnostics_enabled=_coerce_bool(base["diagnostics_enabled"], fallback.diagnostics_enabled),
        diagnostics_limit=diagnostics_limit,
        log_level=level,
    )


def load_shell_settings(path: Path, *, defaults: ShellSettings | None = None) -> ShellSettings:
    path = Path(path)
    if not path.is_file():
        return _normalized({}, defaults)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return _normalized({}, defaults)
    return _normalized(raw if isinstance(raw, dict) else {}, defaults)


def save_shell_settings(path: Path, settings: ShellSettings) -> ShellSettings:
    path = Path(path)
    normalized = _normalized(asdict(settings), settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(asdict(normalized), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return normalized
