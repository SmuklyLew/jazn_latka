from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write(relative: str, text: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, *, label: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    return updated


# 1. Single version source.
version_path = "latka_jazn/version.py"
version = read(version_path)
version = regex_once(
    version,
    r'DISTRIBUTION_VERSION\s*=\s*"15\.0\.3\.3"',
    'DISTRIBUTION_VERSION = "15.0.3.4"',
    label="distribution version",
)
version = regex_once(
    version,
    r'PACKAGE_VERSION\s*=\s*"v15\.0\.3\.3"',
    'PACKAGE_VERSION = "v15.0.3.4"',
    label="package version",
)
write(version_path, version)


# 2. Case-insensitive option normalization. Values and user text remain untouched.
write(
    "latka_jazn/core/cli_normalization.py",
    '''from __future__ import annotations

import argparse
from collections.abc import Sequence


_OPTION_ALIASES = {
    "--chatgpt": "--chat-gpt",
    "--chat_gpt": "--chat-gpt",
}


def normalize_cli_argv(argv: Sequence[str], parser: argparse.ArgumentParser) -> list[str]:
    """Normalize known option names without modifying values or user text.

    Only tokens before the standalone ``--`` separator are considered. Known
    option names are matched case-insensitively. Values, paths, session IDs,
    model names and the message after ``--`` are preserved exactly.
    """

    canonical: dict[str, str] = {}
    for action in parser._actions:
        for option in action.option_strings:
            canonical[option.casefold()] = option
    canonical.update(_OPTION_ALIASES)

    normalized: list[str] = []
    after_separator = False
    for token in argv:
        if after_separator:
            normalized.append(token)
            continue
        if token == "--":
            normalized.append(token)
            after_separator = True
            continue
        if not token.startswith("-"):
            normalized.append(token)
            continue

        option, separator, value = token.partition("=")
        replacement = canonical.get(option.casefold())
        if replacement is None:
            normalized.append(token)
            continue
        normalized.append(replacement + (separator + value if separator else ""))
    return normalized
''',
)


# 3. Separate visible channel from the selected language backend.
write(
    "latka_jazn/core/runtime_environment.py",
    '''from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from typing import Any, Mapping, TextIO

from latka_jazn.version import schema_version

CHATGPT_ADAPTER = "chatgpt_runtime_adapter"
TERMINAL_ADAPTER = "terminal_runtime_adapter"
OPENAI_ADAPTER = "openai_responses_adapter"
OLLAMA_ADAPTER = "local_llm_adapter"
LMSTUDIO_ADAPTER = "lmstudio_runtime_adapter"
OPENAI_COMPATIBLE_ADAPTER = "openai_compatible_local_adapter"
CODEX_ADAPTER = "codex_development_adapter"
NULL_ADAPTER = "null_model_adapter"

_CHATGPT_COMMANDS = {"--chat-gpt", "--chat-gpt-final-only"}
_TERMINAL_COMMANDS = {"--chat", "--loop"}
_OPENAI_COMMANDS = {"--chat-open-ai"}
_LMSTUDIO_COMMANDS = {"--chat-lm-studio"}
_LOCAL_LLM_COMMANDS = {"--local-llm"}


def _adapter_name(config: Any) -> str:
    raw = str(getattr(config, "model_adapter", "null") or "null").strip().casefold()
    if raw in {"", "null", "none", "null_model_adapter", "auto"}:
        return NULL_ADAPTER
    if raw in {"chatgpt", "chatgpt_runtime", "chatgpt_runtime_adapter", "chat_gpt", "chat-gpt"}:
        return CHATGPT_ADAPTER
    if raw in {"chat", "terminal", "terminal_runtime", "terminal_runtime_adapter", "local_terminal", "chat_loop"}:
        return TERMINAL_ADAPTER
    if raw in {"openai", "openai_responses", "openai_responses_adapter"}:
        return OPENAI_ADAPTER
    if raw in {"local", "ollama", "local_llm", "local_llm_adapter"}:
        return OLLAMA_ADAPTER
    if raw in {"lmstudio", "lm_studio", "lmstudio_runtime", "lmstudio_runtime_adapter"}:
        return LMSTUDIO_ADAPTER
    if raw in {"openai_compatible", "openai_compatible_local", "openai_compatible_local_adapter"}:
        return OPENAI_COMPATIBLE_ADAPTER
    if raw in {"codex", "codex_development", "codex_development_adapter"}:
        return CODEX_ADAPTER
    return raw


def _truthy_env(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "tak", "on"}


def _normalize_channel(value: str | None) -> str | None:
    raw = str(value or "").strip().casefold().replace("_", "-")
    if raw in {"chatgpt", "chat-gpt", "chatgpt-host", "openai-chatgpt", "host-chatgpt"}:
        return "chatgpt"
    if raw in {"terminal", "chat", "cli", "local-terminal", "terminal-chat"}:
        return "terminal"
    if raw in {"openai", "openai-api", "responses", "responses-api"}:
        return "openai"
    if raw in {"ollama", "local-llm", "local"}:
        return "ollama"
    if raw in {"null", "none", "offline"}:
        return "null"
    return None


def _stream_isatty(stream: TextIO | None) -> bool | None:
    if stream is None:
        return None
    try:
        return bool(stream.isatty())
    except Exception:
        return None


def _detected_openai_chatgpt_tool_container(env: Mapping[str, str]) -> bool:
    if _truthy_env(env.get("JAZN_ASSUME_CHATGPT_HOST")):
        return True
    if env.get("JAZN_HOST_RUNTIME", "").strip().casefold() in {"chatgpt", "chatgpt_host", "openai_chatgpt"}:
        return True
    if env.get("JAZN_VISIBLE_CHANNEL", "").strip().casefold() in {"chatgpt", "chatgpt_host", "openai_chatgpt"}:
        return True
    if "JUPYTER_SERVER_OAI_PATH" in env:
        return True
    return any(key.startswith("CUA_DD_") for key in env)


@dataclass(slots=True)
class RuntimeEnvironmentStatus:
    explicit_command: str | None
    selected_backend_adapter: str
    visible_channel_adapter: str | None
    effective_runtime_adapter: str
    environment_host: str
    detection_basis: list[str]
    stdin_isatty: bool | None
    stdout_isatty: bool | None
    is_chatgpt_host_bridge: bool
    is_terminal_chat_loop: bool
    uses_openai_api: bool
    requires_openai_api_key: bool
    schema_version: str = schema_version("runtime_environment")
    truth_boundary: str = (
        "Środowisko i kanał widzialnej rozmowy są oddzielone od backendu modelu. "
        "chatgpt_runtime_adapter oznacza kanał hosta ChatGPT, nie lokalne wywołanie modelu ChatGPT. "
        "terminal_runtime_adapter opisuje kanał terminala; backendem językowym może być Ollama. "
        "null_model_adapter pozostaje prawdomównym fallbackiem bez modelu."
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        configured_backend = self.selected_backend_adapter
        payload["configured_backend_adapter"] = configured_backend
        payload["programmatic_backend_adapter"] = configured_backend
        payload["selected_backend_adapter"] = self.effective_runtime_adapter
        payload["selection_scope"] = "effective_runtime_channel"
        payload["host_bridge_external_generation_required"] = bool(self.is_chatgpt_host_bridge)
        return payload


def detect_runtime_environment(
    config: Any,
    *,
    command: str | None = None,
    env: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    infer_host_environment: bool = False,
) -> RuntimeEnvironmentStatus:
    env_map: Mapping[str, str] = env if env is not None else os.environ
    selected = _adapter_name(config)
    raw_explicit = str(command or "").strip() or None
    explicit = "--chat-gpt" if raw_explicit in _CHATGPT_COMMANDS else raw_explicit
    universal_chat = explicit in _TERMINAL_COMMANDS
    visible: str | None = None
    host = "unknown"
    basis: list[str] = []
    uses_openai = False
    requires_key = False

    if explicit in _CHATGPT_COMMANDS:
        visible = CHATGPT_ADAPTER
        host = "chatgpt_explicit_command"
        basis.append(f"explicit_command:{explicit}")
    elif explicit in _OPENAI_COMMANDS:
        visible = OPENAI_ADAPTER
        host = "openai_api_explicit_command"
        basis.append(f"explicit_command:{explicit}")
        uses_openai = True
        requires_key = True
    elif explicit in _LMSTUDIO_COMMANDS:
        visible = LMSTUDIO_ADAPTER
        host = "lmstudio_explicit_command"
        basis.append(f"explicit_command:{explicit}")
    elif explicit in _LOCAL_LLM_COMMANDS:
        visible = OLLAMA_ADAPTER
        host = "ollama_explicit_command"
        basis.append(f"explicit_command:{explicit}")

    if visible is None:
        channel = _normalize_channel(env_map.get("JAZN_VISIBLE_CHANNEL") or env_map.get("JAZN_HOST_RUNTIME"))
        if channel == "chatgpt":
            visible = CHATGPT_ADAPTER
            host = "chatgpt_env_marker"
            basis.append("env:JAZN_VISIBLE_CHANNEL/JAZN_HOST_RUNTIME")
        elif channel == "terminal":
            visible = TERMINAL_ADAPTER
            host = "terminal_env_marker"
            basis.append("env:JAZN_VISIBLE_CHANNEL/JAZN_HOST_RUNTIME")
        elif channel == "openai":
            visible = OPENAI_ADAPTER
            host = "openai_api_env_marker"
            basis.append("env:JAZN_VISIBLE_CHANNEL/JAZN_HOST_RUNTIME")
            uses_openai = True
            requires_key = True
        elif channel == "ollama":
            visible = OLLAMA_ADAPTER
            host = "ollama_env_marker"
            basis.append("env:JAZN_VISIBLE_CHANNEL/JAZN_HOST_RUNTIME")
        elif channel == "null":
            host = "null_env_marker"
            basis.append("env:JAZN_VISIBLE_CHANNEL/JAZN_HOST_RUNTIME")

    if visible is None and infer_host_environment and _detected_openai_chatgpt_tool_container(env_map):
        visible = CHATGPT_ADAPTER
        host = "openai_chatgpt_tool_container"
        basis.append("detected_openai_chatgpt_tool_container")

    if visible is None and universal_chat:
        visible = TERMINAL_ADAPTER
        host = "terminal_universal_chat"
        basis.append(f"explicit_command:{explicit}")

    if visible is None and selected in {
        CHATGPT_ADAPTER,
        TERMINAL_ADAPTER,
        OPENAI_ADAPTER,
        OLLAMA_ADAPTER,
        LMSTUDIO_ADAPTER,
        OPENAI_COMPATIBLE_ADAPTER,
    }:
        visible = selected
        host = f"configured_{selected}"
        basis.append("config.model_adapter")

    if visible == TERMINAL_ADAPTER:
        effective = selected if selected not in {NULL_ADAPTER, TERMINAL_ADAPTER} else TERMINAL_ADAPTER
    else:
        effective = visible or selected
    if effective == "null":
        effective = NULL_ADAPTER
    if effective == OPENAI_ADAPTER:
        uses_openai = True
        requires_key = True
    if not basis:
        basis.append("config.model_adapter_default")

    return RuntimeEnvironmentStatus(
        explicit_command=explicit,
        selected_backend_adapter=selected,
        visible_channel_adapter=visible,
        effective_runtime_adapter=effective,
        environment_host=host,
        detection_basis=basis,
        stdin_isatty=_stream_isatty(stdin if stdin is not None else sys.stdin),
        stdout_isatty=_stream_isatty(stdout if stdout is not None else sys.stdout),
        is_chatgpt_host_bridge=visible == CHATGPT_ADAPTER,
        is_terminal_chat_loop=visible == TERMINAL_ADAPTER,
        uses_openai_api=uses_openai,
        requires_openai_api_key=requires_key,
    )


def apply_effective_runtime_adapter(config: Any, environment: RuntimeEnvironmentStatus) -> Any:
    effective = environment.effective_runtime_adapter
    if effective == NULL_ADAPTER:
        setattr(config, "model_adapter", "null")
    else:
        setattr(config, "model_adapter", effective)
    if effective == CHATGPT_ADAPTER and not os.environ.get("JAZN_MODEL_NAME"):
        setattr(config, "model_name", os.environ.get("JAZN_CHATGPT_MODEL_NAME", "chatgpt_host_model").strip() or "chatgpt_host_model")
    if environment.visible_channel_adapter == TERMINAL_ADAPTER and not os.environ.get("JAZN_TERMINAL_MODEL_NAME"):
        setattr(config, "terminal_model_name", "terminal_visible_layer")
    return config
''',
)


# 4. Universal route: confirmed ChatGPT host -> Ollama -> paid OpenAI (explicitly allowed) -> null.
write(
    "latka_jazn/core/llm_route_resolver.py",
    '''from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from latka_jazn.core.runtime_environment import (
    CHATGPT_ADAPTER,
    NULL_ADAPTER,
    OLLAMA_ADAPTER,
    OPENAI_ADAPTER,
    detect_runtime_environment,
)
from latka_jazn.version import schema_version

LLM_ROUTE_AUTO = "auto"
ROUTE_LOCAL = "ollama_local"
ROUTE_CHATGPT_BRIDGE = "chatgpt_host_bridge"
ROUTE_OPENAI_PAID = "openai_api_paid"
ROUTE_NULL = "null_fallback"

_ALLOWED_MODES = {"auto", "local", "chatgpt_bridge", "openai_api", "none"}


def _env_get(env: Mapping[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = env.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "tak", "on"}


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


def _http_json(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _model_names(payload: dict[str, Any]) -> list[str]:
    result: list[str] = []
    models = payload.get("models")
    if isinstance(models, list):
        for item in models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("model") or item.get("name") or "").strip()
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
    for path, target in (("/api/ps", running), ("/api/tags", installed)):
        try:
            data = _http_json(base_url + path, timeout_seconds=timeout_seconds)
            target.extend(_model_names(data))
            endpoint_reachable = True
        except HTTPError as exc:
            errors.append(f"{path}:http_{exc.code}")
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            errors.append(f"{path}:unavailable")

    union = list(dict.fromkeys([*running, *installed]))
    selected = ""
    reason = "ollama_unavailable"
    if configured_model:
        if configured_model in union:
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
    paid_allowed = _truthy(env_map.get("JAZN_ALLOW_PAID_OPENAI")) if "JAZN_ALLOW_PAID_OPENAI" in env_map else bool(getattr(config, "allow_paid_openai_api", False))
    api_key_present = bool(str(env_map.get("OPENAI_API_KEY") or "").strip())
    openai_model = _env_get(env_map, "JAZN_OPENAI_MODEL", "JAZN_MODEL_NAME", default=str(getattr(config, "openai_paid_model_name", getattr(config, "model_name", "")) or ""))

    environment = detect_runtime_environment(
        config,
        command=command,
        env=env_map,
        infer_host_environment=infer_host_environment,
    )
    bridge_available = bool(environment.is_chatgpt_host_bridge)

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
            "available": bool(configured),
            "endpoint_reachable": None,
            "reason": "probe_skipped",
            "errors": [],
        }
    local_status = {
        "checked": True,
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
        "checked": True,
        "available": bridge_available,
        "adapter": CHATGPT_ADAPTER,
        "basis": list(environment.detection_basis),
        "environment_host": environment.environment_host,
        "truth_boundary": "Host bridge oznacza, że widzialną wypowiedź tworzy host ChatGPT; lokalny Python nie wywołuje modelu ChatGPT.",
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
            return status(True, ROUTE_CHATGPT_BRIDGE, "forced ChatGPT host bridge available", adapter=CHATGPT_ADAPTER)
        return status(False, ROUTE_NULL, "forced ChatGPT host bridge unavailable", error="chatgpt_bridge_unavailable", adapter=NULL_ADAPTER)
    if mode == "openai_api":
        if not api_key_present:
            return status(False, ROUTE_NULL, "forced OpenAI API route blocked: OPENAI_API_KEY missing", error="openai_api_key_missing", adapter=NULL_ADAPTER)
        if not paid_allowed:
            return status(False, ROUTE_NULL, "forced OpenAI API route blocked: JAZN_ALLOW_PAID_OPENAI is not 1", error="paid_openai_not_allowed", adapter=NULL_ADAPTER)
        return status(True, ROUTE_OPENAI_PAID, "forced paid OpenAI API route allowed", adapter=OPENAI_ADAPTER)

    if bridge_available:
        return status(True, ROUTE_CHATGPT_BRIDGE, "confirmed ChatGPT host bridge available", adapter=CHATGPT_ADAPTER)
    if selected_local:
        return status(True, ROUTE_LOCAL, "local Ollama endpoint and model available", adapter=OLLAMA_ADAPTER)
    if api_key_present and paid_allowed:
        return status(True, ROUTE_OPENAI_PAID, "host and Ollama unavailable; paid OpenAI API explicitly allowed", adapter=OPENAI_ADAPTER)
    return status(True, ROUTE_NULL, "no host bridge, no usable Ollama model, and paid OpenAI API unavailable or not allowed", adapter=NULL_ADAPTER)


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
''',
)


# 5. Make --chat use the universal resolver while retaining explicit compatibility routes.
contract_path = "latka_jazn/core/chat_command_contract.py"
contract = read(contract_path)
contract = replace_once(
    contract,
    '''def apply_chat_cli_settings(config: JaznConfig) -> JaznConfig:
    """Select the truthful local terminal adapter for the --chat loop."""
    config.model_adapter = "terminal_runtime_adapter"
    if not os.environ.get("JAZN_TERMINAL_MODEL_NAME"):
        config.terminal_model_name = "terminal_visible_layer"
    return config
''',
    '''def apply_chat_cli_settings(
    config: JaznConfig,
    *,
    infer_host_environment: bool = True,
    probe_local: bool = True,
) -> JaznConfig:
    """Resolve the universal ``--chat`` language route for this environment."""
    from latka_jazn.core.llm_route_resolver import apply_llm_route_to_config, build_llm_route_status

    route_status = build_llm_route_status(
        config,
        command="--chat",
        infer_host_environment=infer_host_environment,
        probe_local=probe_local,
    )
    apply_llm_route_to_config(config, route_status)
    if not os.environ.get("JAZN_TERMINAL_MODEL_NAME"):
        config.terminal_model_name = "terminal_visible_layer"
    return config
''',
    label="apply_chat_cli_settings",
)
write(contract_path, contract)


# 6. Main technical entry point: diagnostics, package-smoke, normalized flags and universal --chat.
main_path = "main.py"
main = read(main_path)
main = replace_once(
    main,
    "from latka_jazn.cli_commands.export import export_payload\n",
    "from latka_jazn.cli_commands.export import export_payload\nfrom latka_jazn.cli_commands.diagnostics import doctor_payload\n",
    label="main doctor import",
)
main = replace_once(
    main,
    "from latka_jazn.core.llm_route_resolver import build_llm_route_status\n",
    "from latka_jazn.core.llm_route_resolver import ROUTE_CHATGPT_BRIDGE, apply_llm_route_to_config, build_llm_route_status\nfrom latka_jazn.core.cli_normalization import normalize_cli_argv\n",
    label="main route imports",
)
main = replace_once(
    main,
    '    parser.add_argument("--root", type=Path, default=None,',
    '    parser.add_argument("--version", action="version", version=PACKAGE_VERSION_FULL)\n'
    '    parser.add_argument("--doctor", action="store_true", help="Uruchom diagnostykę pakietu i kontraktów bez rozpoczynania rozmowy.")\n'
    '    parser.add_argument("--package-smoke", action="store_true", dest="package_smoke", help="Uruchom kontrolę gotowości paczki.")\n'
    '    parser.add_argument("--package-profile", choices=("development", "system", "release", "export-without-git", "memory", "full"), default="system")\n'
    '    parser.add_argument("--root", type=Path, default=None,',
    label="main parser diagnostic options",
)
main = replace_once(
    main,
    'parser.add_argument("--chat-gpt", action="store_true"',
    'parser.add_argument("--chat-gpt", "--chatgpt", action="store_true"',
    label="chatgpt alias",
)
main = replace_once(
    main,
    'parser.add_argument("--local-llm", action="store_true"',
    'parser.add_argument("--local-llm", "--ollama", action="store_true"',
    label="ollama alias",
)
main = replace_once(
    main,
    '    parser.add_argument("--daemon-status", action="store_true", dest="daemon_status",',
    '    parser.add_argument("--daemon-status", action="store_true", dest="daemon_status",',
    label="daemon status anchor",
)
# Insert snapshot after the complete daemon-status declaration without depending on mojibake help text.
main = regex_once(
    main,
    r'(    parser\.add_argument\("--daemon-status"[^\n]*\n)',
    r'\1    parser.add_argument("--daemon-snapshot", action="store_true", dest="daemon_snapshot", help="Z --daemon-status nie sonduj endpointu; pokaż marker, PID i heartbeat.")\n',
    label="daemon snapshot option",
)
main = replace_once(
    main,
    '''    argv = list(sys.argv[1:] if argv is None else argv)
    if "--chat-jsonl" in argv:
''',
    '''    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    argv = normalize_cli_argv(argv, parser)
    if "--chat-jsonl" in argv:
''',
    label="normalize argv",
)
main = replace_once(
    main,
    "    parser = _build_parser()\n    ns = parser.parse_args(argv)\n",
    "    ns = parser.parse_args(argv)\n",
    label="single parser construction",
)
main = replace_once(
    main,
    "    runtime_root = (root or Path(__file__).resolve().parent).resolve()\n\n    if ns.runtime_preflight:\n",
    '''    runtime_root = (root or Path(__file__).resolve().parent).resolve()

    if ns.doctor:
        payload = doctor_payload(runtime_root)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if payload.get("ok") else 1

    if ns.package_smoke:
        from latka_jazn.tools.release_readiness import build_release_readiness_report

        payload = build_release_readiness_report(runtime_root, profile=ns.package_profile)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return int(payload.get("exit_code", 2))

    if ns.runtime_preflight:
''',
    label="main diagnostics dispatch",
)
main = replace_once(
    main,
    '''    if ns.final_only and not ns.chat_gpt:
        parser.error("--final-only jest legacy aliasem i wymaga kanonicznego --chat-gpt")

    if ns.bridge_discovery:
''',
    '''    if ns.final_only and not ns.chat_gpt:
        parser.error("--final-only jest legacy aliasem i wymaga kanonicznego --chat-gpt")

    # --chat is the universal route. A confirmed ChatGPT host wins; otherwise
    # local Ollama is probed and the runtime falls back truthfully without a model.
    if ns.chat_loop and not ns.chat_gpt:
        cfg = config or JaznConfig()
        route_status = build_llm_route_status(
            cfg,
            command="--chat",
            infer_host_environment=True,
            probe_local=True,
        )
        apply_llm_route_to_config(cfg, route_status)
        config = cfg
        if route_status.selected_route == ROUTE_CHATGPT_BRIDGE:
            ns.chat_gpt = True
            ns.chat_loop = False

    if ns.bridge_discovery:
''',
    label="universal chat dispatch",
)
main = replace_once(
    main,
    '''        print(json.dumps(status_daemon(
            cfg,
            host=ns.daemon_host,
            port=ns.daemon_port,
            marker_output=ns.daemon_marker_output,
        ), ensure_ascii=False, indent=2, sort_keys=True))
''',
    '''        print(json.dumps(status_daemon(
            cfg,
            host=ns.daemon_host,
            port=ns.daemon_port,
            marker_output=ns.daemon_marker_output,
            probe_endpoint=not ns.daemon_snapshot,
        ), ensure_ascii=False, indent=2, sort_keys=True))
''',
    label="daemon snapshot dispatch",
)
main = replace_once(
    main,
    "        cfg = apply_chat_cli_settings(config or JaznConfig())\n",
    "        cfg = config or apply_chat_cli_settings(JaznConfig(), infer_host_environment=True, probe_local=True)\n",
    label="chat loop routed config",
)
write(main_path, main)


# 7. Ollama native chat endpoint.
local_adapter_path = "latka_jazn/model_adapters/local_llm_adapter.py"
local_adapter = read(local_adapter_path)
local_adapter = replace_once(
    local_adapter,
    '''        payload = {
            "model": self.model,
            "stream": False,
            "system": (
                "Jesteś językową warstwą wykonawczą Jaźni Łatki. Odpowiadaj po polsku i naturalnie. "
                "Nie wymyślaj pamięci ani faktów poza przekazanym kontekstem."
            ),
            "prompt": request.prompt
            + "\\n\\nKONTEKST_JAZNI_JSON:\\n"
            + json.dumps(request.system_context or {}, ensure_ascii=False),
            "options": {"num_predict": self.max_output_tokens},
        }
''',
    '''        system_text = (
            "Jesteś językową warstwą wykonawczą Jaźni Łatki. Odpowiadaj po polsku i naturalnie. "
            "Nie wymyślaj pamięci ani faktów poza przekazanym kontekstem."
            "\\n\\nKONTEKST_JAZNI_JSON:\\n"
            + json.dumps(request.system_context or {}, ensure_ascii=False)
        )
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": request.prompt},
            ],
            "options": {"num_predict": self.max_output_tokens},
        }
''',
    label="ollama chat payload",
)
local_adapter = replace_once(local_adapter, 'f"{self.api_base}/api/generate"', 'f"{self.api_base}/api/chat"', label="ollama endpoint")
local_adapter = replace_once(
    local_adapter,
    '            text = str(data.get("response") or "").strip()\n',
    '            message = data.get("message") if isinstance(data.get("message"), dict) else {}\n            text = str(message.get("content") or data.get("response") or "").strip()\n',
    label="ollama response content",
)
local_adapter = replace_once(local_adapter, 'endpoint_used="/api/generate"', 'endpoint_used="/api/chat"', label="ollama endpoint status")
write(local_adapter_path, local_adapter)


# 8. Daemon always uses the technical main.py entry point, never the operator CLI.
daemon_path = "latka_jazn/core/runtime_daemon.py"
daemon = read(daemon_path)
daemon = replace_once(
    daemon,
    '    start_file = find_start_file(root) or root / "main.py"\n',
    '    start_file = root / "main.py" if (root / "main.py").is_file() else (find_start_file(root) or root / "main.py")\n',
    label="daemon main entrypoint",
)
write(daemon_path, daemon)


# 9. Versioned frame marker and focused regressions.
engine_path = "latka_jazn/core/engine.py"
engine = read(engine_path)
engine = engine.replace("truth_boundary_check/v15.0.3.3-frame", "truth_boundary_check/v15.0.3.4-frame")
write(engine_path, engine)

write(
    "tests/test_v15034_startup_stability.py",
    '''from __future__ import annotations

import json
from pathlib import Path

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core.cli_normalization import normalize_cli_argv
from latka_jazn.core.llm_route_resolver import (
    ROUTE_CHATGPT_BRIDGE,
    ROUTE_LOCAL,
    ROUTE_NULL,
    apply_llm_route_to_config,
    build_llm_route_status,
    probe_ollama,
)
from latka_jazn.core.runtime_daemon import build_daemon_start_command
from latka_jazn.core.runtime_environment import (
    CHATGPT_ADAPTER,
    NULL_ADAPTER,
    OLLAMA_ADAPTER,
    TERMINAL_ADAPTER,
    detect_runtime_environment,
)
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


class _FakeStream:
    def __init__(self, is_tty: bool) -> None:
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


class _Response:
    def __init__(self, payload: dict) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._data


def _ollama_probe(*, available: bool = True) -> dict:
    return {
        "provider": "ollama",
        "adapter": OLLAMA_ADAPTER,
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen3:8b" if available else "",
        "configured_model": "",
        "running_models": ["qwen3:8b"] if available else [],
        "installed_models": ["qwen3:8b"] if available else [],
        "available": available,
        "endpoint_reachable": available,
        "reason": "single_running_model" if available else "ollama_unavailable",
        "errors": [] if available else ["/api/ps:unavailable", "/api/tags:unavailable"],
    }


def test_cli_flags_are_case_insensitive_but_message_and_values_are_preserved() -> None:
    parser = main_module._build_parser()
    argv = normalize_cli_argv(
        ["--CHATGPT", "--SESSION-ID", "DomA", "--", "Czy --STATUS działa?"],
        parser,
    )
    assert argv == ["--chat-gpt", "--session-id", "DomA", "--", "Czy --STATUS działa?"]
    ns = parser.parse_args(argv)
    assert ns.chat_gpt is True
    assert ns.session_id == "DomA"
    assert ns.message == ["--", "Czy --STATUS działa?"]


def test_main_parser_exposes_operator_compatibility_flags() -> None:
    parser = main_module._build_parser()
    ns = parser.parse_args(["--doctor"])
    assert ns.doctor is True
    ns = parser.parse_args(["--package-smoke", "--package-profile", "system"])
    assert ns.package_smoke is True
    assert ns.package_profile == "system"
    ns = parser.parse_args(["--ollama"])
    assert ns.local_llm is True
    ns = parser.parse_args(["--daemon-status", "--daemon-snapshot"])
    assert ns.daemon_snapshot is True


def test_universal_chat_prefers_confirmed_chatgpt_host(monkeypatch, tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    monkeypatch.setattr("latka_jazn.core.llm_route_resolver.probe_ollama", lambda *_a, **_k: _ollama_probe())
    status = build_llm_route_status(
        cfg,
        command="--chat",
        env={"JAZN_VISIBLE_CHANNEL": "chatgpt"},
        infer_host_environment=True,
    )
    assert status.selected_route == ROUTE_CHATGPT_BRIDGE
    assert status.selected_adapter == CHATGPT_ADAPTER


def test_universal_chat_terminal_keeps_ollama_as_backend(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path, model_adapter=OLLAMA_ADAPTER, local_model_name="qwen3:8b")
    environment = detect_runtime_environment(
        cfg,
        command="--chat",
        env={},
        stdin=_FakeStream(True),
        stdout=_FakeStream(True),
        infer_host_environment=False,
    )
    assert environment.visible_channel_adapter == TERMINAL_ADAPTER
    assert environment.effective_runtime_adapter == OLLAMA_ADAPTER
    assert environment.is_terminal_chat_loop is True


def test_ollama_discovery_prefers_single_running_model(monkeypatch, tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)

    def fake_urlopen(request, timeout):
        if str(request.full_url).endswith("/api/ps"):
            return _Response({"models": [{"model": "qwen3:8b"}]})
        return _Response({"models": [{"name": "qwen3:8b"}, {"name": "gemma3:4b"}]})

    monkeypatch.setattr("latka_jazn.core.llm_route_resolver.urlopen", fake_urlopen)
    result = probe_ollama(cfg, {})
    assert result["available"] is True
    assert result["model"] == "qwen3:8b"
    assert result["reason"] == "single_running_model"


def test_universal_chat_selects_ollama_when_host_is_absent(monkeypatch, tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    monkeypatch.setattr("latka_jazn.core.llm_route_resolver.probe_ollama", lambda *_a, **_k: _ollama_probe())
    status = build_llm_route_status(cfg, command="--chat", env={}, infer_host_environment=False)
    assert status.selected_route == ROUTE_LOCAL
    apply_llm_route_to_config(cfg, status)
    assert cfg.model_adapter == OLLAMA_ADAPTER
    assert cfg.local_model_name == "qwen3:8b"


def test_universal_chat_uses_truthful_null_fallback(monkeypatch, tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    monkeypatch.setattr("latka_jazn.core.llm_route_resolver.probe_ollama", lambda *_a, **_k: _ollama_probe(available=False))
    status = build_llm_route_status(cfg, command="--chat", env={}, infer_host_environment=False)
    assert status.selected_route == ROUTE_NULL
    assert status.selected_adapter == NULL_ADAPTER


def test_ollama_adapter_uses_native_chat_endpoint(monkeypatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response({"message": {"role": "assistant", "content": "Cześć"}, "done": True})

    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", fake_urlopen)
    adapter = LocalLlmAdapter(model="qwen3:8b")
    response = adapter.generate(ModelAdapterRequest(prompt="Hej", system_context={"route": "ordinary"}))
    assert captured["url"].endswith("/api/chat")
    assert [item["role"] for item in captured["payload"]["messages"]] == ["system", "user"]
    assert response.text == "Cześć"
    assert response.endpoint_used == "/api/chat"


def test_daemon_technical_process_always_starts_through_main_py(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "run.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
    command = build_daemon_start_command(tmp_path)
    assert Path(command[1]).name == "main.py"
    assert "--daemon-run" in command
''',
)

print("v15.0.3.4 startup stability source edits staged")
