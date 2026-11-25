from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request
from latka_jazn.core.ollama_inference_policy import (
    ollama_cloud_model_name, ollama_model_identity, ollama_remote_model_entry,
)

from latka_jazn.core.runtime_environment import (
    CHATGPT_ADAPTER,
    NULL_ADAPTER,
    OLLAMA_ADAPTER,
    OPENAI_ADAPTER,
    detect_runtime_environment,
)
from latka_jazn.version import schema_version
from latka_jazn.core.conversation_entrypoint_contract import (
    ROUTE_CHATGPT_HOST,
    ROUTE_NULL_FALLBACK,
    ROUTE_OLLAMA_LOCAL,
    ROUTE_OPENAI_PAID as CONTRACT_ROUTE_OPENAI_PAID,
)

LLM_ROUTE_AUTO = "auto"
ROUTE_LOCAL = ROUTE_OLLAMA_LOCAL
ROUTE_CHATGPT_BRIDGE = ROUTE_CHATGPT_HOST
ROUTE_OPENAI_PAID = CONTRACT_ROUTE_OPENAI_PAID
ROUTE_NULL = ROUTE_NULL_FALLBACK

_ALLOWED_MODES = {"auto", "local", "chatgpt_bridge", "openai_api", "none"}


def _env_get(env: Mapping[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = env.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "tak", "on"}


def paid_openai_allowed(config: Any, env: Mapping[str, str]) -> bool:
    """One opt-in policy shared by routing and direct factory construction."""
    if getattr(config, "paid_openai_turn_denied", False) or not getattr(config, "allow_network", True):
        return False
    if "JAZN_ALLOW_PAID_OPENAI" in env:
        return _truthy(env.get("JAZN_ALLOW_PAID_OPENAI"))
    return bool(getattr(config, "allow_paid_openai_api", False))


def _normalize_mode(value: str | None) -> str:
    raw = str(value or "auto").strip().casefold().replace("-", "_") or "auto"
    aliases = {
        "local_llm": "local",
        "local_openai_compatible": "local",
        "ollama": "local",
        "chatgpt": "chatgpt_bridge",
        "chat_gpt": "chatgpt_bridge",
        "bridge": "chatgpt_bridge",
        "openai": "openai_api",
        "openai_paid": "openai_api",
        "paid_openai": "openai_api",
        "null": "none",
        "fallback": "none",
        "off": "none",
    }
    mode = aliases.get(raw, raw)
    return mode if mode in _ALLOWED_MODES else "auto"


def _ollama_base_url(value: str) -> str:
    base = str(value or "http://127.0.0.1:11434").strip().rstrip("/")
    for suffix in ("/api", "/v1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base or "http://127.0.0.1:11434"


def urlopen(request: Request, *, timeout: float) -> Any:
    # Lazy import avoids resolver/factory initialization cycles.
    from latka_jazn.model_adapters.model_http_transport import open_local_model_request
    return open_local_model_request(request, timeout=timeout)


def _http_json(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _model_names(payload: dict[str, Any], blocked: set[str]) -> list[str]:
    result: list[str] = []
    models = payload.get("models")
    if isinstance(models, list):
        for item in models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("model") or item.get("name") or "").strip()
            if ollama_remote_model_entry(item):
                for field in ("name", "model"):
                    alias = str(item.get(field) or "").strip()
                    if alias:
                        blocked.add(ollama_model_identity(alias))
                continue
            if name and name not in result:
                result.append(name)
    return result


def probe_ollama(
    config: Any,
    env: Mapping[str, str],
    *,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    base_url = _ollama_base_url(
        _env_get(
            env,
            "JAZN_OLLAMA_BASE_URL",
            "JAZN_LOCAL_LLM_BASE_URL",
            "JAZN_LOCAL_LLM_API_BASE",
            "JAZN_LOCAL_MODEL_API_BASE",
            default=str(getattr(config, "local_model_api_base", "http://127.0.0.1:11434") or "http://127.0.0.1:11434"),
        )
    )
    configured_model = _env_get(
        env,
        "JAZN_OLLAMA_MODEL",
        "JAZN_LOCAL_LLM_MODEL",
        "JAZN_LOCAL_MODEL_NAME",
        default=str(getattr(config, "local_model_name", "") or "").strip(),
    )
    running: list[str] = []
    installed: list[str] = []
    errors: list[str] = []
    endpoint_reachable = False
    blocked: set[str] = set()
    for path, target in (("/api/ps", running), ("/api/tags", installed)):
        try:
            data = _http_json(base_url + path, timeout_seconds=timeout_seconds)
            target.extend(_model_names(data, blocked))
            endpoint_reachable = True
        except HTTPError as exc:
            errors.append(f"{path}:http_{exc.code}")
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            errors.append(f"{path}:unavailable")

    running = [name for name in running if ollama_model_identity(name) not in blocked]
    installed = [name for name in installed if ollama_model_identity(name) not in blocked]
    union = list(dict.fromkeys([*running, *installed]))
    selected = ""
    reason = "ollama_unavailable"
    if configured_model:
        if ollama_cloud_model_name(configured_model) or ollama_model_identity(configured_model) in blocked:
            reason = "ollama_cloud_model_not_authorized"
        elif configured_model in union:
            selected = configured_model
            reason = "configured_model_available"
        elif endpoint_reachable:
            reason = "configured_model_not_installed"
    elif len(running) == 1:
        selected = running[0]
        reason = "single_running_model"
    elif len(installed) == 1:
        selected = installed[0]
        reason = "single_installed_model"
    elif len(union) > 1:
        reason = "ollama_model_ambiguous"
    elif endpoint_reachable:
        reason = "ollama_has_no_models"

    return {
        "provider": "ollama",
        "adapter": OLLAMA_ADAPTER,
        "base_url": base_url,
        "model": selected,
        "configured_model": configured_model,
        "running_models": running,
        "installed_models": installed,
        "available": bool(endpoint_reachable and selected),
        "endpoint_reachable": endpoint_reachable,
        "reason": reason,
        "errors": errors,
    }


@dataclass(slots=True)
class LlmRouteStatus:
    ok: bool
    route_mode: str
    selected_route: str
    paid_route: bool
    paid_route_allowed: bool
    local: dict[str, Any]
    chatgpt_bridge: dict[str, Any]
    openai_api: dict[str, Any]
    reason: str
    error: str | None = None
    selected_adapter: str | None = None
    schema_version: str = schema_version("llm_route_status")
    truth_boundary: str = (
        "Routing wybiera wykonawcę językowego, nie tożsamość Jaźni. "
        "Potwierdzony host ChatGPT ma pierwszeństwo; w terminalu lokalnym wykrywana jest Ollama. "
        "Płatne OpenAI API wymaga jawnego trybu, OPENAI_API_KEY i JAZN_ALLOW_PAID_OPENAI=1."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_llm_route_status(
    config: Any,
    *,
    command: str | None = None,
    env: Mapping[str, str] | None = None,
    infer_host_environment: bool = False,
    probe_local: bool = True,
) -> LlmRouteStatus:
    env_map: Mapping[str, str] = env if env is not None else os.environ
    mode = _normalize_mode(env_map.get("JAZN_LLM_ROUTE") or str(getattr(config, "llm_route_mode", "auto") or "auto"))
    paid_allowed = paid_openai_allowed(config, env_map)
    api_key_present = bool(str(env_map.get("OPENAI_API_KEY") or "").strip())
    openai_model = _env_get(env_map, "JAZN_OPENAI_MODEL", "JAZN_MODEL_NAME", default=str(getattr(config, "openai_paid_model_name", getattr(config, "model_name", "")) or ""))

    environment = detect_runtime_environment(
        config,
        command=command,
        env=env_map,
        infer_host_environment=infer_host_environment,
    )
    # A declared host channel is not evidence that a remote generator is ready.
    bridge_declared = bool(environment.is_chatgpt_host_bridge)
    # Host-visible channel selection is a phase-2 request, not live MCP proof.
    # Remote readiness and accepted finalization are checked by the host gate.
    bridge_available = bridge_declared

    if probe_local:
        local_probe = probe_ollama(config, env_map)
    else:
        configured = _env_get(env_map, "JAZN_OLLAMA_MODEL", "JAZN_LOCAL_LLM_MODEL", default=str(getattr(config, "local_model_name", "") or ""))
        local_probe = {
            "provider": "ollama",
            "adapter": OLLAMA_ADAPTER,
            "base_url": _ollama_base_url(str(getattr(config, "local_model_api_base", "http://127.0.0.1:11434"))),
            "model": configured,
            "configured_model": configured,
            "running_models": [],
            "installed_models": [],
            "available": False,
            "endpoint_reachable": None,
            "reason": "probe_skipped_unverified",
            "errors": [],
        }
    local_status = {
        "checked": bool(probe_local),
        "available": bool(local_probe.get("available")),
        "provider": "ollama",
        "adapter": OLLAMA_ADAPTER,
        "base_url": local_probe.get("base_url"),
        "model": local_probe.get("model") or None,
        "selected_candidate": local_probe if local_probe.get("available") else None,
        "candidate": local_probe,
        "reason": local_probe.get("reason"),
    }
    selected_local = local_probe if local_probe.get("available") else None

    chatgpt_status = {
        "checked": False,
        "available": bridge_available,
        "declared": bridge_declared,
        "generation_verified": False,
        "availability_scope": "host_visible_generation_request_not_live_mcp",
        "adapter": CHATGPT_ADAPTER,
        "basis": list(environment.detection_basis),
        "environment_host": environment.environment_host,
        "truth_boundary": "Host bridge wybiera kanał dla zewnętrznej phase-2, nie dowodzi gotowości MCP ani zaakceptowanej odpowiedzi. Lokalny Python nie wywołuje modelu ChatGPT.",
    }
    openai_status = {
        "checked": True,
        "api_key_present": api_key_present,
        "allowed": paid_allowed,
        "model": openai_model or None,
        "paid_route": bool(api_key_present and paid_allowed),
    }

    def status(ok: bool, route: str, reason: str, *, error: str | None = None, adapter: str | None = None) -> LlmRouteStatus:
        return LlmRouteStatus(
            ok=ok,
            route_mode=mode,
            selected_route=route,
            paid_route=(route == ROUTE_OPENAI_PAID),
            paid_route_allowed=paid_allowed,
            local=local_status,
            chatgpt_bridge=chatgpt_status,
            openai_api=openai_status,
            reason=reason,
            error=error,
            selected_adapter=adapter,
        )

    if mode == "none":
        return status(True, ROUTE_NULL, "JAZN_LLM_ROUTE=none", adapter=NULL_ADAPTER)
    if mode == "local":
        if selected_local:
            return status(True, ROUTE_LOCAL, "forced Ollama route available", adapter=OLLAMA_ADAPTER)
        return status(False, ROUTE_NULL, "forced Ollama route unavailable", error="local_llm_unavailable", adapter=NULL_ADAPTER)
    if mode == "chatgpt_bridge":
        if bridge_available:
            return status(True, ROUTE_CHATGPT_BRIDGE, "explicit ChatGPT host finalization requested; live readiness unverified", adapter=CHATGPT_ADAPTER)
        return status(False, ROUTE_NULL, "forced ChatGPT host bridge unavailable", error="chatgpt_bridge_unavailable", adapter=NULL_ADAPTER)
    if mode == "openai_api":
        if not api_key_present:
            return status(False, ROUTE_NULL, "forced OpenAI API route blocked: OPENAI_API_KEY missing", error="openai_api_key_missing", adapter=NULL_ADAPTER)
        if not paid_allowed:
            return status(False, ROUTE_NULL, "forced OpenAI API route blocked: JAZN_ALLOW_PAID_OPENAI is not 1", error="paid_openai_not_allowed", adapter=NULL_ADAPTER)
        return status(True, ROUTE_OPENAI_PAID, "forced paid OpenAI API route allowed", adapter=OPENAI_ADAPTER)

    if bridge_available:
        return status(True, ROUTE_CHATGPT_BRIDGE, "ChatGPT visible channel selected; readiness must be verified externally", adapter=CHATGPT_ADAPTER)
    if selected_local:
        return status(True, ROUTE_LOCAL, "local Ollama endpoint and model available", adapter=OLLAMA_ADAPTER)
    # Auto selection must not silently send local or private context to paid
    # external inference. Explicit openai_api mode is the only authorized route.
    if api_key_present and paid_allowed:
        return status(True, ROUTE_NULL, "paid API configured but auto external transfer disabled", adapter=NULL_ADAPTER)
    return status(True, ROUTE_NULL, "no verified host generation or usable Ollama model; core remains available without a generative model", adapter=NULL_ADAPTER)


def apply_llm_route_to_config(config: Any, route_status: LlmRouteStatus) -> Any:
    route = route_status.selected_route
    if route == ROUTE_LOCAL:
        candidate = route_status.local.get("selected_candidate") if isinstance(route_status.local, dict) else None
        if isinstance(candidate, dict):
            setattr(config, "model_adapter", OLLAMA_ADAPTER)
            setattr(config, "local_model_name", str(candidate.get("model") or ""))
            setattr(config, "local_model_api_base", str(candidate.get("base_url") or ""))
        return config
    if route == ROUTE_CHATGPT_BRIDGE:
        setattr(config, "model_adapter", CHATGPT_ADAPTER)
        return config
    if route == ROUTE_OPENAI_PAID:
        setattr(config, "model_adapter", OPENAI_ADAPTER)
        return config
    setattr(config, "model_adapter", NULL_ADAPTER)
    return config
