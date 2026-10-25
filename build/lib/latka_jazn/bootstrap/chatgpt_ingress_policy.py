from __future__ import annotations

from enum import Enum


class ChatGptEntryAction(str, Enum):
    """Host entry gate; never an MCP tool-registration or runtime lifecycle."""

    CHECK_REMOTE_STATUS = "check_remote_status"
    USE_REMOTE_RUNTIME = "use_remote_runtime"
    PROBE_LOCAL_PROCESS = "probe_local_process"
    VERIFY_LOCAL_SYSTEM = "verify_local_system"
    START_OR_RESUME_LOCAL = "start_or_resume_local"
    USE_LOCAL_RUNTIME = "use_local_runtime"
    HOST_DIAGNOSTIC = "host_diagnostic"


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

def select_chatgpt_entry_action(
    *,
    ingress_mode: ChatGptIngressMode | str = ChatGptIngressMode.HYBRID_ADAPTIVE,
    complete_remote_toolset: bool = False,
    remote_ready: bool | None = None,
    local_process_created: bool | None = None,
    verified_system: bool = False,
    local_runtime_ready: bool = False,
) -> ChatGptEntryAction:
    """Pick the next host gate; the local SYSTEM never requires MCP tools.

    This policy does not execute the gate or submit a user turn. External host
    tools, not this code, control process allocation and its wall-clock delay.
    """
    mode = normalize_chatgpt_ingress_mode(ingress_mode)
    if remote_ready is True and not complete_remote_toolset:
        raise ValueError("remote_ready_requires_current_message_complete_toolset")
    if complete_remote_toolset:
        if remote_ready is None:
            return ChatGptEntryAction.CHECK_REMOTE_STATUS
        if remote_ready:
            return ChatGptEntryAction.USE_REMOTE_RUNTIME

    if mode is ChatGptIngressMode.REMOTE_ONLY:
        return ChatGptEntryAction.HOST_DIAGNOSTIC
    if local_runtime_ready:
        if not verified_system:
            raise ValueError("local_ready_requires_verified_system")
        return ChatGptEntryAction.USE_LOCAL_RUNTIME
    if local_process_created is None:
        return ChatGptEntryAction.PROBE_LOCAL_PROCESS
    if not local_process_created:
        # Existing bounded-alternative policy is evaluated separately.
        return ChatGptEntryAction.HOST_DIAGNOSTIC
    if not verified_system:
        return ChatGptEntryAction.VERIFY_LOCAL_SYSTEM
    return ChatGptEntryAction.START_OR_RESUME_LOCAL


__all__ = [
    "ChatGptEntryAction",
    "ChatGptIngressMode",
    "automatic_handoff_allowed",
    "local_executor_fallback_allowed",
    "normalize_chatgpt_ingress_mode",
    "select_chatgpt_entry_action",
]
