from __future__ import annotations

import copy
import os
import re
from typing import Any, Mapping


CANONICAL_CHAT_COMMAND = "--chat"
CANONICAL_CHATGPT_COMMAND = "--chat-gpt"
CANONICAL_OLLAMA_COMMAND = "--chat-ollama"
CANONICAL_OPENAI_COMMAND = "--chat-open-ai"
DEFAULT_CANONICAL_CHAT_SESSION_ID = "jazn-main"

_COMMAND_ALIASES: dict[str, str] = {
    "--chat-gpt-final-only": CANONICAL_CHATGPT_COMMAND,
    "--local-llm": CANONICAL_OLLAMA_COMMAND,
    "--ollama": CANONICAL_OLLAMA_COMMAND,
    "--chat-openai": CANONICAL_OPENAI_COMMAND,
    "direct_message": CANONICAL_CHAT_COMMAND,
}

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:@-]{1,128}$")

MODEL_CHANNEL_CONFIG_FIELDS: tuple[str, ...] = (
    "llm_route_mode",
    "allow_paid_openai_api",
    "openai_paid_model_name",
    "model_adapter",
    "model_name",
    "model_api_base",
    "model_timeout_seconds",
    "model_max_output_tokens",
    "local_model_name",
    "local_model_api_base",
    "llama_cpp_model_name",
    "llama_cpp_model_api_base",
)

_STRING_FIELDS = frozenset(
    {
        "llm_route_mode",
        "openai_paid_model_name",
        "model_adapter",
        "model_name",
        "model_api_base",
        "local_model_name",
        "local_model_api_base",
        "llama_cpp_model_name",
        "llama_cpp_model_api_base",
    }
)
_BOOL_FIELDS = frozenset({"allow_paid_openai_api"})
_FLOAT_FIELDS = frozenset({"model_timeout_seconds"})
_INT_FIELDS = frozenset({"model_max_output_tokens"})


def canonical_chat_command(value: str | None) -> str:
    """Return one canonical public conversation command.

    The command chooses the language/model channel only. It must never select a
    different Jaźń identity, memory owner, session owner, or finalization owner.
    """

    normalized = str(value or CANONICAL_CHAT_COMMAND).strip().lower()
    normalized = _COMMAND_ALIASES.get(normalized, normalized)
    if normalized == CANONICAL_CHAT_COMMAND or normalized.startswith("--chat-"):
        return normalized
    raise ValueError(f"unsupported_chat_command:{value!r}")


def resolve_canonical_chat_session_id(
    value: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Resolve the stable default session shared by every chat adapter."""

    source = os.environ if env is None else env
    candidate = (
        str(value or "").strip()
        or str(source.get("JAZN_CANONICAL_CHAT_SESSION_ID") or "").strip()
        or str(source.get("JAZN_CHAT_SESSION_ID") or "").strip()
        or DEFAULT_CANONICAL_CHAT_SESSION_ID
    )
    if not _SESSION_ID_RE.fullmatch(candidate):
        raise ValueError("session_id_contains_unsafe_characters_or_invalid_length")
    return candidate


def normalize_model_channel_config(
    payload: Mapping[str, Any] | None,
) -> dict[str, str | bool | float | int]:
    """Validate the non-secret, turn-scoped model/channel configuration.

    Credentials, auth headers, arbitrary environment variables, and nested
    objects are intentionally not representable by this contract.
    """

    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise TypeError("model_channel_config_must_be_mapping")

    unknown = sorted(str(key) for key in payload if str(key) not in MODEL_CHANNEL_CONFIG_FIELDS)
    if unknown:
        raise ValueError("model_channel_config_unknown_fields:" + ",".join(unknown))

    normalized: dict[str, str | bool | float | int] = {}
    for field in MODEL_CHANNEL_CONFIG_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if value is None:
            continue
        if field in _STRING_FIELDS:
            normalized[field] = str(value).strip()
            continue
        if field in _BOOL_FIELDS:
            if not isinstance(value, bool):
                raise TypeError(f"model_channel_config_boolean_required:{field}")
            normalized[field] = value
            continue
        if field in _FLOAT_FIELDS:
            if isinstance(value, bool):
                raise TypeError(f"model_channel_config_number_required:{field}")
            number = float(value)
            if number <= 0.0:
                raise ValueError(f"model_channel_config_positive_required:{field}")
            normalized[field] = number
            continue
        if field in _INT_FIELDS:
            if isinstance(value, bool):
                raise TypeError(f"model_channel_config_integer_required:{field}")
            number = int(value)
            if number <= 0:
                raise ValueError(f"model_channel_config_positive_required:{field}")
            normalized[field] = number
            continue
        raise ValueError(f"model_channel_config_unhandled_field:{field}")
    return normalized


def model_channel_config_from_config(config: Any) -> dict[str, str | bool | float | int]:
    """Project the safe provider/channel settings needed to reproduce a turn."""

    raw = {
        field: getattr(config, field)
        for field in MODEL_CHANNEL_CONFIG_FIELDS
        if hasattr(config, field)
    }
    return normalize_model_channel_config(raw)


def apply_model_channel_config(
    config: Any,
    payload: Mapping[str, Any] | None,
) -> Any:
    """Return a shallow config copy with only approved per-turn fields changed."""

    normalized = normalize_model_channel_config(payload)
    if not normalized:
        return config
    routed = copy.copy(config)
    for field, value in normalized.items():
        setattr(routed, field, value)
    return routed


def model_channel_public_metadata(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Expose bounded observability without serializing endpoint/model values."""

    normalized = normalize_model_channel_config(payload)
    return {
        "configured": bool(normalized),
        "fields": sorted(normalized),
        "contains_credentials": False,
    }
