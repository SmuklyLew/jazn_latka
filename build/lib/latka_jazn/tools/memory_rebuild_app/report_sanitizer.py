from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import os
import re


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _looks_absolute_path(value: str) -> bool:
    if not value:
        return False
    if os.path.isabs(value):
        return True
    return len(value) >= 3 and value[1:3] in {":\\", ":/"}


_SAFE_ENUM_KEYS = frozenset({
    "schema_version", "source_kind", "source_family", "role", "truth_domain",
    "pipeline", "source_mode", "parse_mode", "status", "outcome", "profile",
    "step_id", "kind", "gate_kind", "baseline_id", "memory_generation",
    "validation_mode", "memory_readiness_class", "readiness_class",
    "layout", "schema_identity", "tool_version", "system_version",
})
_SAFE_VALUE_RE = re.compile(r"^[a-zA-Z0-9_.:/+-]{1,128}$")
_SAFE_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{0,95}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _redact_key(key: str) -> str:
    """Arbitrary mapping keys may themselves be filenames or PII."""
    if _SAFE_KEY_RE.fullmatch(key) and not _looks_absolute_path(key):
        return key
    return "private_key_" + _sha(key)[:16]


def sanitize_report(value: Any, *, key: str = "") -> Any:
    """Fail-closed transport view: unknown text is never copied verbatim.

    This is a shareable *summary*, not a lossless copy of the private report.
    Unlike path-only redaction, it covers arbitrary messages, filenames,
    identifiers, exception strings and dynamic mapping keys.
    """
    if isinstance(value, dict):
        return {_redact_key(str(k)): sanitize_report(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_report(item, key=key) for item in value]
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        if _looks_absolute_path(value):
            return {
                "private_locator_removed": True,
                "locator_sha256": _sha(value),
                "suffix": Path(value).suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", Path(value).suffix) else "",
            }
        if (key.endswith("sha256") or key.endswith("_fingerprint")) and _SHA256_RE.fullmatch(value):
            return value.lower()
        if key in _SAFE_ENUM_KEYS and _SAFE_VALUE_RE.fullmatch(value):
            return value
        return {"private_text_removed": True, "length": len(value)}
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return {"unsupported_value_removed": True}


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
