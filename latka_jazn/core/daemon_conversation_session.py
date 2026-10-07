from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_channel import (
    canonical_chat_command,
    model_channel_config_from_config,
    normalize_model_channel_config,
    resolve_canonical_chat_session_id,
)
from latka_jazn.core.runtime_daemon import (
    DEFAULT_DAEMON_CHAT_TIMEOUT_SECONDS,
    DEFAULT_DAEMON_HOST,
    DEFAULT_DAEMON_PORT,
    chat_daemon,
)


class DaemonConversationSession:
    """Transport view of one daemon-owned canonical conversation session.

    This object never creates a JaznEngine, memory store, identity owner, or
    finalization authority. Closing the client only disconnects this adapter;
    the persistent daemon remains the owner of the session lifecycle.
    """

    runtime_turn_timeout_managed = True
    persistent_runtime_owner = "daemon"
    engine_reused_between_turns = True

    def __init__(
        self,
        config: JaznConfig,
        *,
        session_id: str | None = None,
        no_carryover: bool = False,
        source_client: str = "daemon_conversation_client",
        command: str = "--chat",
        host: str = DEFAULT_DAEMON_HOST,
        port: int = DEFAULT_DAEMON_PORT,
        wait_timeout_seconds: float | None = None,
        model_channel_config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.command = canonical_chat_command(command)
        self.session_id = resolve_canonical_chat_session_id(session_id)
        self.no_carryover = bool(no_carryover)
        self.source_client = str(source_client or "daemon_conversation_client")
        self.host = str(host)
        self.port = int(port)
        self.wait_timeout_seconds = max(
            0.1,
            float(
                wait_timeout_seconds
                if wait_timeout_seconds is not None
                else getattr(
                    config,
                    "daemon_chat_execution_timeout_seconds",
                    DEFAULT_DAEMON_CHAT_TIMEOUT_SECONDS,
                )
            ),
        )
        self.model_channel_config = normalize_model_channel_config(
            model_channel_config
            if model_channel_config is not None
            else model_channel_config_from_config(config)
        )
        self.state = SimpleNamespace(session_id=self.session_id)
        self._reset_session_pending = bool(no_carryover)
        self._closed = False

    @property
    def usable(self) -> bool:
        return not self._closed

    def process_user_text(self, user_text: str, **kwargs: Any) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("DaemonConversationSession is closed")
        text = str(user_text or "").strip()
        if not text:
            return {
                "ok": False,
                "error_code": "empty_message",
                "session": {"session_id": self.session_id},
            }

        request_id = str(
            kwargs.get("request_id")
            or kwargs.get("_request_id")
            or ""
        ).strip() or None
        effective_command = canonical_chat_command(
            str(kwargs.get("command") or self.command)
        )
        channel_override = kwargs.get("model_channel_config")
        effective_channel = normalize_model_channel_config(
            channel_override
            if isinstance(channel_override, dict)
            else self.model_channel_config
        )
        effective_client = str(kwargs.get("client") or self.source_client)
        timeout_override = kwargs.get("_timeout_seconds_override")
        wait_timeout = (
            max(0.1, float(timeout_override))
            if timeout_override is not None
            else self.wait_timeout_seconds
        )
        result = chat_daemon(
            self.config,
            text,
            host=self.host,
            port=self.port,
            session_id=self.session_id,
            no_carryover=self.no_carryover,
            client=effective_client,
            command=effective_command,
            model_channel_config=effective_channel,
            reset_session=self._reset_session_pending,
            request_id=request_id,
            timeout=wait_timeout,
        )
        if result.get("accepted") is True or result.get("ok") is True:
            self._reset_session_pending = False
        result.setdefault("session", {"session_id": self.session_id})
        result["conversation_session_authority"] = {
            "owner": "persistent_daemon",
            "session_id": self.session_id,
            "command": effective_command,
            "adapter_is_session_owner": False,
            "client_close_stops_runtime": False,
        }
        return result

    def close(self) -> None:
        """Disconnect this client view without stopping the persistent runtime."""

        self._closed = True
