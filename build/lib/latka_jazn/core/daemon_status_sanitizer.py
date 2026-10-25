from __future__ import annotations

"""Pure status projection for the canonical Jaźń daemon.

Explicit decoration at the API definition site replaces late global and
handler monkey-patches that previously depended on module import order.
"""

from functools import wraps
from typing import Any, Callable, ParamSpec

_Params = ParamSpec("_Params")

STATUS_TEXT_REPLACEMENTS = {
    "albo" + "wstrzyknięty": "albo wstrzyknięty",
    "brak" + "nie": "brak nie",
    "blokuje" + "zwykłej": "blokuje zwykłej",
    "proces" + "daemonu": "proces daemonu",
    "endpoint" + "nie": "endpoint nie",
    "nie" + "blokuje": "nie blokuje",
    "PID" + "dają": "PID dają",
    "active_state" + "depends": "active_state depends",
}


def sanitize_status_payload(value: Any) -> Any:
    if isinstance(value, str):
        for old, new in STATUS_TEXT_REPLACEMENTS.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, dict):
        return {key: sanitize_status_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_status_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_status_payload(item) for item in value)
    return value


def sanitized_daemon_status(
    operation: Callable[_Params, dict[str, Any]],
) -> Callable[_Params, dict[str, Any]]:
    """Sanitize a public status result without modifying the global symbol."""
    @wraps(operation)
    def call(*args: _Params.args, **kwargs: _Params.kwargs) -> dict[str, Any]:
        result = operation(*args, **kwargs)
        return sanitize_status_payload(result)
    return call


__all__ = ["STATUS_TEXT_REPLACEMENTS", "sanitize_status_payload", "sanitized_daemon_status"]
