from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeGuard


def is_json_object(value: object) -> TypeGuard[dict[str, Any]]:
    """Return true only for mutable JSON objects with string keys."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def json_object(value: object) -> dict[str, Any]:
    """Return the original JSON object or a fail-closed empty object."""
    return value if is_json_object(value) else {}


def is_string_keyed_mapping(value: object) -> TypeGuard[Mapping[str, Any]]:
    """Return true for read-only JSON-object views with string keys."""
    return isinstance(value, Mapping) and all(isinstance(key, str) for key in value)


def mapping_object(value: object) -> Mapping[str, Any]:
    """Return a string-keyed mapping or a fail-closed empty mapping."""
    return value if is_string_keyed_mapping(value) else {}
