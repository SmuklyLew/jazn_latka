from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import os


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _looks_absolute_path(value: str) -> bool:
    if not value:
        return False
    if os.path.isabs(value):
        return True
    return len(value) >= 3 and value[1:3] in {":\\", ":/"}


def sanitize_report(value: Any, *, key: str = "") -> Any:
    """Remove absolute/private path material while preserving auditability.

    Sanitized reports keep hashes and structural metadata, never source path text.
    Private reports are written separately by ``write_report_pair``.
    """
    if isinstance(value, dict):
        return {str(k): sanitize_report(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_report(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [sanitize_report(item, key=key) for item in value]
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str) and _looks_absolute_path(value):
        path = Path(value)
        return {
            "private_locator_removed": True,
            "locator_sha256": _sha(value),
            "suffix": path.suffix,
        }
    return value


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def write_report_pair(report_dir: str | Path, stem: str, payload: Any) -> dict[str, str]:
    root = Path(report_dir).expanduser().resolve()
    private_path = root / f"{stem}.private.json"
    sanitized_path = root / f"{stem}.sanitized.json"
    _atomic_json(private_path, payload)
    _atomic_json(sanitized_path, sanitize_report(payload))
    return {"private": str(private_path), "sanitized": str(sanitized_path)}


__all__ = ["sanitize_report", "write_report_pair"]
