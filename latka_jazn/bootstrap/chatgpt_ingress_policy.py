from __future__ import annotations

from enum import Enum


class ChatGptIngressMode(str, Enum):
    """Execution policy for ChatGPT host ingress.

    HYBRID_ADAPTIVE is the normal ChatGPT conversation path. It prefers a
    verified current-message remote Jaźń app/runtime, but permits a bounded
    host-local executor/bootstrap fallback before the user turn is submitted.
    REMOTE_ONLY remains an explicit strict mode with no local/process fallback.
    OPERATOR_RECOVERY remains an explicit service mode for Codex/Work/local
    operators that intentionally need local bootstrap, recovery, or handoff.
    """

    HYBRID_ADAPTIVE = "hybrid_adaptive"
    REMOTE_ONLY = "remote_only"
    OPERATOR_RECOVERY = "operator_recovery"


def normalize_chatgpt_ingress_mode(value: object) -> ChatGptIngressMode:
    if isinstance(value, ChatGptIngressMode):
        return value
    candidate = str(value or ChatGptIngressMode.HYBRID_ADAPTIVE.value).strip().lower()
    try:
        return ChatGptIngressMode(candidate)
    except ValueError as exc:
        raise ValueError(f"unsupported_chatgpt_ingress_mode:{candidate}") from exc


def local_executor_fallback_allowed(value: object) -> bool:
    return normalize_chatgpt_ingress_mode(value) in {
        ChatGptIngressMode.HYBRID_ADAPTIVE,
        ChatGptIngressMode.OPERATOR_RECOVERY,
    }


def automatic_handoff_allowed(value: object) -> bool:
    """Return whether host handoff may participate in the selected ingress mode."""

    return (
        normalize_chatgpt_ingress_mode(value)
        is ChatGptIngressMode.OPERATOR_RECOVERY
    )


__all__ = [
    "ChatGptIngressMode",
    "automatic_handoff_allowed",
    "local_executor_fallback_allowed",
    "normalize_chatgpt_ingress_mode",
]
