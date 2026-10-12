from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from latka_jazn.version import schema_version


CANONICAL_CHAT_COMMAND = "--chat"
CANONICAL_CHATGPT_COMMAND = "--chat-gpt"
CANONICAL_OLLAMA_COMMAND = "--chat-ollama"
CANONICAL_OPENAI_COMMAND = "--chat-open-ai"

ROUTE_CHATGPT_HOST = "chatgpt_host_bridge"
ROUTE_OLLAMA_LOCAL = "ollama_local"
ROUTE_OPENAI_PAID = "openai_api_paid"
ROUTE_NULL_FALLBACK = "null_fallback"

AUTO_ROUTE_PRIORITY: tuple[str, ...] = (
    ROUTE_CHATGPT_HOST,
    ROUTE_OLLAMA_LOCAL,
    ROUTE_OPENAI_PAID,
    ROUTE_NULL_FALLBACK,
)

ConversationEntrypointRole = Literal[
    "universal_conversation",
    "chatgpt_host_bridge",
    "ollama_local_backend",
    "openai_api_backend",
]


@dataclass(frozen=True, slots=True)
class ConversationEntrypointContract:
    """Public conversation-entrypoint semantics independent of provider code.

    The runtime owns session/turn state, memory, identity lineage, tools and
    finalization.  Entrypoints only select a visible/model channel.  Keeping
    this contract lightweight lets CLI, discovery and host adapters share one
    source of truth without importing the full conversation engine.
    """

    command: str
    operator_command: str
    role: ConversationEntrypointRole
    route_mode: str
    route_priority: tuple[str, ...]
    requires_api_key: bool
    uses_openai_api: bool
    host_finalization_policy: str
    persistent_runtime_preferred: bool
    compatibility_aliases: tuple[str, ...] = ()
    schema_version: str = schema_version("conversation_entrypoint_contract")
    truth_boundary: str = (
        "Publiczna komenda wybiera kanał wykonawczy języka, nie właściciela Jaźni. "
        "Stan sesji i tury, pamięć, narzędzia, lineage oraz finalizacja pozostają własnością runtime."
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def conversation_entrypoint_contract(command: str) -> ConversationEntrypointContract:
    normalized = str(command or "").strip()
    if normalized == CANONICAL_CHAT_COMMAND:
        return ConversationEntrypointContract(
            command=CANONICAL_CHAT_COMMAND,
            operator_command="run.py chat",
            role="universal_conversation",
            route_mode="auto",
            route_priority=AUTO_ROUTE_PRIORITY,
            requires_api_key=False,
            uses_openai_api=False,
            host_finalization_policy="required_only_when_chatgpt_host_route_selected",
            persistent_runtime_preferred=True,
            compatibility_aliases=("--loop",),
        )
    if normalized in {CANONICAL_CHATGPT_COMMAND, "--chat-gpt-final-only"}:
        return ConversationEntrypointContract(
            command=CANONICAL_CHATGPT_COMMAND,
            operator_command="run.py chat-gpt",
            role="chatgpt_host_bridge",
            route_mode="chatgpt_bridge",
            route_priority=(ROUTE_CHATGPT_HOST,),
            requires_api_key=False,
            uses_openai_api=False,
            host_finalization_policy="two_phase_action_first",
            persistent_runtime_preferred=True,
            compatibility_aliases=("--chat-gpt-final-only", "--chat-gpt --final-only"),
        )
    if normalized in {CANONICAL_OLLAMA_COMMAND, "--local-llm", "--ollama"}:
        return ConversationEntrypointContract(
            command=CANONICAL_OLLAMA_COMMAND,
            operator_command="run.py chat-ollama",
            role="ollama_local_backend",
            route_mode="local",
            route_priority=(ROUTE_OLLAMA_LOCAL,),
            requires_api_key=False,
            uses_openai_api=False,
            host_finalization_policy="runtime_owned_visible_finalization",
            persistent_runtime_preferred=True,
            compatibility_aliases=("--local-llm", "--ollama"),
        )
    if normalized in {CANONICAL_OPENAI_COMMAND, "--chat-openai"}:
        return ConversationEntrypointContract(
            command=CANONICAL_OPENAI_COMMAND,
            operator_command="run.py chat --backend openai-api (target contract); current compatibility: main.py --chat-open-ai",
            role="openai_api_backend",
            route_mode="openai_api",
            route_priority=(ROUTE_OPENAI_PAID,),
            requires_api_key=True,
            uses_openai_api=True,
            host_finalization_policy="runtime_owned_visible_finalization",
            persistent_runtime_preferred=True,
            compatibility_aliases=("--chat-openai",),
        )
    raise ValueError(f"unknown conversation entrypoint: {command!r}")


def auto_route_priority_text(separator: str = " -> ") -> str:
    return separator.join(AUTO_ROUTE_PRIORITY)
