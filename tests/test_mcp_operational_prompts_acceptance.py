from __future__ import annotations

from pathlib import Path

from latka_jazn.mcp.operator_prompts import (
    FOCUS_VALUES, PROMPT_NAME, complete_runtime_prompt, get_runtime_prompt,
    list_runtime_prompts,
)
from latka_jazn.mcp.server import (
    MCP_PROTOCOL_VERSION_MODERN, META_CLIENT_CAPABILITIES, META_PROTOCOL_VERSION,
    JaznMcpServer,
)


def _request(method: str, **params: object) -> dict:
    return {"jsonrpc": "2.0", "id": 42, "method": method, "params": {
        **params, "_meta": {
            META_PROTOCOL_VERSION: MCP_PROTOCOL_VERSION_MODERN,
            META_CLIENT_CAPABILITIES: {},
        },
    }}


def test_operational_prompts_and_completion_are_read_only_and_stateless(tmp_path: Path) -> None:
    server = JaznMcpServer(root=tmp_path, allow_unauthenticated_local_test=True)
    discovered = server.handle(_request("server/discover"))
    assert discovered is not None
    assert "prompts" in discovered["result"]["capabilities"]
    assert "completions" in discovered["result"]["capabilities"]
    listed = server.handle(_request("prompts/list"))
    assert listed is not None
    assert listed["result"]["prompts"] == list_runtime_prompts()["prompts"]
    assert listed["result"]["cacheScope"] == "public"
    for focus in FOCUS_VALUES:
        response = server.handle(_request("prompts/get", name=PROMPT_NAME, arguments={"focus": focus}))
        assert response is not None
        assert response["result"]["messages"] == get_runtime_prompt(
            {"name": PROMPT_NAME, "arguments": {"focus": focus}}
        )["messages"]
        content = response["result"]["messages"][0]["content"]["text"]
        assert "does not activate" in content and "jazn_status" in content if focus == "readiness" else "does not activate" in content
    prefix = server.handle(_request("completion/complete", ref={"type": "ref/prompt", "name": PROMPT_NAME}, argument={"name": "focus", "value": "f"}))
    assert prefix is not None
    assert prefix["result"]["completion"]["values"] == ["finalization"]
    assert complete_runtime_prompt({"type": "ref/prompt", "name": PROMPT_NAME}, {"name": "focus", "value": "f"})["completion"]["hasMore"] is False
    for method, payload in [
        ("prompts/get", {"name": PROMPT_NAME, "arguments": {"focus": "../../private"}}),
        ("completion/complete", {"ref": {"type": "ref/prompt", "name": "missing"}, "argument": {"name": "focus", "value": ""}}),
    ]:
        rejected = server.handle(_request(method, **payload))
        assert rejected is not None and rejected["error"]["code"] == -32602
