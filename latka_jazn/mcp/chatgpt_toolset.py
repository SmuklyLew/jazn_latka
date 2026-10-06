from __future__ import annotations

"""Current-message ChatGPT app/tool exposure evidence for Jaźń."""

import hashlib
from typing import Any


REQUIRED_CHATGPT_TURN_TOOLS: tuple[str, ...] = (
    "jazn_status",
    "jazn_generate_visible_reply",
    "jazn_resume_visible_reply",
    "jazn_finalize_reply",
)
CHATGPT_TOOLSET_REVISION = "jazn_chatgpt_turn_toolset/v2"
REQUIRED_CHATGPT_TURN_TOOLS_SHA256 = hashlib.sha256(
    ("\n".join(REQUIRED_CHATGPT_TURN_TOOLS) + "\n").encode("utf-8")
).hexdigest()


def _normalize_tool_names(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("callable_tool_names_must_be_array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("callable_tool_name_must_be_string")
        name = item.strip()
        if not name:
            raise ValueError("callable_tool_name_must_be_nonempty")
        if len(name) > 128:
            raise ValueError("callable_tool_name_too_long")
        if name not in result:
            result.append(name)
    return tuple(sorted(result))


def classify_current_message_toolset(
    callable_tool_names: object,
    *,
    current_message_toolset_observed: bool | None,
) -> dict[str, Any]:
    """Require the complete Jaźń turn surface for this exact ChatGPT message."""

    callable_names = _normalize_tool_names(callable_tool_names)
    observed = current_message_toolset_observed is True
    missing = tuple(
        name for name in REQUIRED_CHATGPT_TURN_TOOLS if name not in callable_names
    )
    ready = observed and not missing
    if not observed:
        reason = "chatgpt_current_message_toolset_not_observed"
    elif missing:
        reason = "chatgpt_required_turn_toolset_incomplete"
    else:
        reason = "chatgpt_required_turn_toolset_ready"
    return {
        "current_message_toolset_observed": observed,
        "required_chatgpt_turn_tools": list(REQUIRED_CHATGPT_TURN_TOOLS),
        "required_chatgpt_turn_tools_revision": CHATGPT_TOOLSET_REVISION,
        "required_chatgpt_turn_tools_sha256": REQUIRED_CHATGPT_TURN_TOOLS_SHA256,
        "callable_chatgpt_tool_names": list(callable_names),
        "missing_required_chatgpt_turn_tools": list(missing),
        "full_turn_toolset_callable": ready,
        "reason_code": reason,
        "truth_boundary": (
            "Only tool names actually exposed by the current ChatGPT message surface count. "
            "Installed/catalog/app metadata, a mention, endpoint configuration, or a previous "
            "message's tool exposure cannot satisfy this gate."
        ),
    }


__all__ = [
    "CHATGPT_TOOLSET_REVISION",
    "REQUIRED_CHATGPT_TURN_TOOLS",
    "REQUIRED_CHATGPT_TURN_TOOLS_SHA256",
    "classify_current_message_toolset",
]
