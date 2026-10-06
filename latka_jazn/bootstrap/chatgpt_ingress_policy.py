from __future__ import annotations

from enum import Enum


class ChatGptIngressMode(str, Enum):
    """Execution policy for ChatGPT host ingress.

    REMOTE_ONLY is the normal ChatGPT conversation path. It never promotes a
    local/process executor, attachment bootstrap, or host handoff into a
    conversation route. OPERATOR_RECOVERY is an explicit service mode for
    Codex/Work/local operators that intentionally need local bootstrap or
    recovery capabilities.
    """

    REMOTE_ONLY = "remote_only"
    OPERATOR_RECOVERY = "operator_recovery"


def normalize_chatgpt_ingress_mode(value: object) -> ChatGptIngressMode:
    if isinstance(value, ChatGptIngressMode):
        return value
    candidate = str(value or ChatGptIngressMode.REMOTE_ONLY.value).strip().lower()
    try:
        return ChatGptIngressMode(candidate)
    except ValueError as exc:
        raise ValueError(f"unsupported_chatgpt_ingress_mode:{candidate}") from exc


def local_executor_fallback_allowed(value: object) -> bool:
    return (
        normalize_chatgpt_ingress_mode(value)
        is ChatGptIngressMode.OPERATOR_RECOVERY
    )


__all__ = [
    "ChatGptIngressMode",
    "local_executor_fallback_allowed",
    "normalize_chatgpt_ingress_mode",
]
