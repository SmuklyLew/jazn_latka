from __future__ import annotations

from dataclasses import asdict, dataclass
import ipaddress
import json
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from latka_jazn.bridge.auth_policy import AuthPolicy, SlidingWindowRateLimiter
from latka_jazn.core.chatgpt_host_pending_store import issue_continuation_token
from latka_jazn.core.runtime_daemon import (
    DAEMON_AUTH_HEADER,
    normalize_daemon_request_id,
    read_daemon_auth_token,
)
from latka_jazn.core.runtime_root import find_runtime_root
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("secure_host_runtime_gateway")


class GatewayError(RuntimeError):
    pass


@dataclass(slots=True)
class GatewayConfig:
    daemon_url: str = "http://127.0.0.1:8787"
    timeout_seconds: float = 15.0
    max_request_bytes: int = 2 * 1024 * 1024
    runtime_root: Path | None = None
    daemon_token: str | None = None
    allowed_tools: tuple[str, ...] = (
        "jazn_generate_visible_reply",
        "jazn_resume_visible_reply",
        "jazn_status",
        "jazn_finalize_reply",
        "jazn_audit_lookup",
    )
    public_ingress_enabled: bool = False
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        if self.public_ingress_enabled:
            raise GatewayError("public_ingress_forbidden_by_default")
        host = self.daemon_url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            if host not in {"localhost"}:
                raise GatewayError("daemon_host_must_be_loopback") from exc
        else:
            if not address.is_loopback:
                raise GatewayError("daemon_host_must_be_loopback")
        if self.runtime_root is not None:
            self.runtime_root = Path(self.runtime_root).expanduser().resolve()


def _poll_runtime_presentation(
    request_id: str,
    *,
    transport_error: str | None = None,
    submit_outcome_authoritative: bool | None = None,
) -> dict[str, Any]:
    presentation: dict[str, Any] = {
        "type": "chatgpt_host_presentation",
        "action": "poll_runtime",
        "phase": "runtime_result_pending",
        "status": "runtime_result_pending",
        "daemon_request_id": request_id,
        "request_id": request_id,
        "poll_command": "jazn_resume_visible_reply",
        "resume_tool": "jazn_resume_visible_reply",
        "host_must_poll_runtime": True,
        "host_must_generate_visible_reply": False,
        "host_reply_finalization_required": False,
        "must_not_resubmit_user_message": True,
        "must_not_claim_runtime_voice": True,
        "must_not_claim_latka_voice": True,
        "submit_outcome_authoritative": submit_outcome_authoritative,
        "safe_recovery": "poll_same_request_id_never_replay_user_message",
        "truth_boundary": (
            "The daemon request id was allocated before the side-effect boundary. "
            "Transport ambiguity must resume/poll this exact request and must never create a second user turn."
        ),
    }
    if transport_error:
        presentation["transport_error"] = transport_error
    return presentation


def _normalize_chat_transport_response(
    value: dict[str, Any],
    *,
    request_id: str,
) -> dict[str, Any]:
    """Normalize daemon transport envelopes without inventing a runtime result."""

    result = dict(value)
    result.setdefault("request_id", request_id)
    nested = result.get("chatgpt_host_presentation")
    if isinstance(nested, dict) and nested.get("action"):
        return result
    if result.get("action"):
        return result

    # The daemon transport can wrap a phase-ready runtime payload in `result`.
    # Unwrap only when that nested payload already owns a host presentation;
    # keep the outer job envelope as evidence instead of manufacturing content.
    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        nested_presentation = nested_result.get("chatgpt_host_presentation")
        if (
            isinstance(nested_presentation, dict)
            and nested_presentation.get("action")
        ) or nested_result.get("action"):
            unwrapped = dict(nested_result)
            unwrapped.setdefault("request_id", request_id)
            unwrapped.setdefault("daemon_job", result)
            return unwrapped

    accepted = result.get("accepted")
    job_status = str(result.get("job_status") or result.get("status") or "").strip()
    pending = bool(
        accepted is not False
        and result.get("phase_result_ready") is not True
        and (
            result.get("done") is False
            or job_status in {
                "queued",
                "running",
                "awaiting_host_finalization",
                "waiting_for_host_finalization",
            }
        )
    )
    if pending:
        result["chatgpt_host_presentation"] = _poll_runtime_presentation(
            request_id,
            submit_outcome_authoritative=True if accepted is True else None,
        )
    return result


class SecureHostRuntimeGateway:
    def __init__(
        self,
        config: GatewayConfig | None = None,
        *,
        auth_policy: AuthPolicy | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self.config = config or GatewayConfig()
        self.config.validate()
        self.auth_policy = auth_policy or AuthPolicy()
        self.rate_limiter = rate_limiter or SlidingWindowRateLimiter()
        self.runtime_root = self.config.runtime_root or find_runtime_root(Path(__file__))

    def authorize(self, *, tool_name: str, token: str | None, subject: str) -> None:
        if tool_name not in self.config.allowed_tools:
            raise GatewayError("tool_not_allowlisted")
        if not self.rate_limiter.allow(subject):
            raise GatewayError("rate_limit_exceeded")
        decision = self.auth_policy.authorize(token, subject=subject)
        if not decision.allowed:
            raise GatewayError(decision.reason)

    def _daemon_token(self) -> str:
        explicit = str(self.config.daemon_token or "").strip()
        if explicit:
            return explicit
        token = read_daemon_auth_token(self.runtime_root)
        if not token:
            raise GatewayError("daemon_auth_token_unavailable")
        return token

    def _http_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if body is not None and len(body) > self.config.max_request_bytes:
            raise GatewayError("request_too_large")
        headers = {
            "Content-Type": "application/json",
            DAEMON_AUTH_HEADER: self._daemon_token(),
        }
        req = request.Request(
            self.config.daemon_url.rstrip("/") + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                data = response.read(self.config.max_request_bytes + 1)
        except error.HTTPError as exc:
            try:
                detail_bytes = exc.read(self.config.max_request_bytes + 1)
                detail = json.loads(detail_bytes.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                detail = {}
            code = str(detail.get("error_code") or detail.get("reason") or f"http_{exc.code}")
            raise GatewayError(f"daemon_rejected:{code}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise GatewayError(f"daemon_unavailable:{type(exc).__name__}") from exc
        if len(data) > self.config.max_request_bytes:
            raise GatewayError("response_too_large")
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise GatewayError("daemon_response_invalid_json") from exc
        if not isinstance(value, dict):
            raise GatewayError("daemon_response_not_object")
        return value

    def status(self) -> dict[str, Any]:
        try:
            daemon = self._http_json("GET", "/status")
            reachable = True
            error_text = None
        except GatewayError as exc:
            daemon = {}
            reachable = False
            error_text = str(exc)
        return {
            "schema_version": SCHEMA_VERSION,
            "gateway_ok": reachable,
            "daemon_reachable": reachable,
            "daemon": daemon,
            "error": error_text,
            "daemon_auth_configured": bool(read_daemon_auth_token(self.runtime_root) or self.config.daemon_token),
            "public_ingress_enabled": False,
            "transport": "loopback_only_authenticated",
            "runtime_root": str(self.runtime_root),
        }

    def chat(
        self,
        message: str,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit one MCP-carried turn with a request id fixed before POST.

        Once `/chat` may have crossed the daemon boundary, a lost response is an
        ambiguous outcome. It is converted to `poll_runtime` for the same id;
        this method never retries the message under a new id and never falls
        back to an independent local turn.
        """

        try:
            daemon_request_id = normalize_daemon_request_id(request_id)
        except ValueError as exc:
            raise GatewayError(str(exc)) from exc
        payload: dict[str, Any] = {
            "message": str(message),
            "client": "secure_mcp_gateway",
            "request_id": daemon_request_id,
        }
        if session_id:
            payload["session_id"] = session_id
        try:
            value = self._http_json("POST", "/chat", payload)
        except GatewayError as exc:
            reason = str(exc)
            if not reason.startswith("daemon_unavailable:"):
                raise
            return {
                "ok": False,
                "accepted": None,
                "done": False,
                "error_code": "daemon_chat_submit_outcome_unknown",
                "request_id": daemon_request_id,
                "submit_outcome_authoritative": False,
                "safe_recovery": "poll_same_request_id_before_any_retry",
                "transport_error": reason,
                "chatgpt_host_presentation": _poll_runtime_presentation(
                    daemon_request_id,
                    transport_error=reason,
                    submit_outcome_authoritative=False,
                ),
            }
        return _normalize_chat_transport_response(value, request_id=daemon_request_id)

    def result(self, request_id: str) -> dict[str, Any]:
        """Poll one existing daemon job without replaying the user turn."""

        normalized = str(request_id or "").strip()
        if not normalized:
            raise GatewayError("daemon_request_id_missing")
        if len(normalized) > 256:
            raise GatewayError("daemon_request_id_too_large")
        query = parse.urlencode({"request_id": normalized})
        return self._http_json("GET", f"/chat-result?{query}")

    def issue_continuation(self, response: dict[str, Any]) -> dict[str, Any]:
        presentation = response.get("chatgpt_host_presentation")
        if not isinstance(presentation, dict):
            presentation = response
        bridge = presentation.get("chatgpt_host_bridge")
        if not isinstance(bridge, dict):
            bridge = response.get("chatgpt_host_bridge")
        if not isinstance(bridge, dict):
            raise GatewayError("host_bridge_contract_missing")
        if str(presentation.get("action") or "") != "generate_then_finalize":
            raise GatewayError("continuation_not_required")
        turn_id = str(bridge.get("turn_id") or presentation.get("turn_id") or "").strip()
        contract_hash = str(bridge.get("host_request_contract_hash") or "").strip().lower()
        if not turn_id or len(contract_hash) != 64:
            raise GatewayError("host_bridge_binding_invalid")
        try:
            return issue_continuation_token(
                self.runtime_root,
                turn_id=turn_id,
                request_contract_hash=contract_hash,
            )
        except Exception as exc:
            if isinstance(exc, GatewayError):
                raise
            raise GatewayError(f"continuation_issue_failed:{type(exc).__name__}:{exc}") from exc

    def note_host_finalization(
        self,
        pending: dict[str, Any],
        *,
        outcome: str,
        reason: str,
        terminal: bool = False,
    ) -> dict[str, Any]:
        binding_value = pending.get("binding")
        binding = binding_value if isinstance(binding_value, dict) else {}
        generation_value = pending.get("generation_context")
        generation = generation_value if isinstance(generation_value, dict) else {}
        request_id = str(
            binding.get("daemon_request_id")
            or generation.get("daemon_request_id")
            or ""
        ).strip()
        if not request_id:
            return {"ok": True, "not_applicable": True, "reason": "one_shot_without_daemon_job"}
        return self._http_json(
            "POST",
            "/chat-finalization",
            {
                "request_id": request_id,
                "turn_id": str(binding.get("turn_id") or ""),
                "trace_id": str(binding.get("trace_id") or ""),
                "request_contract_hash": str(pending.get("request_contract_hash") or ""),
                "outcome": str(outcome),
                "reason": str(reason),
                "terminal": bool(terminal),
            },
        )
