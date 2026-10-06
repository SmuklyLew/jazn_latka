from __future__ import annotations

"""Compatibility names for the canonical ConversationRunner.

The alias is the same class, so daemon factory identity and existing injected
test sessions keep working without constructing or owning a second session.
"""
from latka_jazn.core.conversation_runner import (
    ConversationRunner,
    _host_finalization_pending as _host_finalization_pending,
    _update_runtime_session_state as _update_runtime_session_state,
)

JaznRuntimeSession = ConversationRunner
