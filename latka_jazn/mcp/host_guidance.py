from __future__ import annotations

"""Single host-facing guidance string shared by legacy and HTTP MCP surfaces.

This is a *transport hint*, not the runtime state machine or authority. The
canonical request and finalization implementations remain in Python.
"""

MCP_HOST_TURN_INSTRUCTIONS = (
    "When the Jaźń app is selected, use jazn_status once to verify readiness "
    "and submit the exact user message with jazn_generate_visible_reply and "
    "one stable request_id. On poll_runtime, call jazn_resume_visible_reply "
    "with the same daemon_request_id; never submit the original message again. "
    "On generate_then_finalize, use only the returned host-generation contract "
    "and finish with jazn_finalize_reply. The HTTP adapter computes the UTF-8 "
    "SHA-256 digest; the runtime still validates and persists the finalization. "
    "Show Jaźń output only for accepted action=display_exact. An installed app, "
    "old tool list or this guidance is not live runtime evidence."
)
