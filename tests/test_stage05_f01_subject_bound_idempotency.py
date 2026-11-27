"""F01: the same tool request cannot replay a different subject's cache."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.mcp.server_legacy_v76 import JaznMcpServer


@pytest.mark.parametrize("explicit_key", [False, True])
def test_cached_generate_is_subject_bound_across_server_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit_key: bool,
) -> None:
    root = tmp_path / "synthetic"
    (root / "local_resources").mkdir(parents=True)
    calls: list[str] = []

    def dispatch(name: str, args: dict[str, Any], *, request_id: str | None = None) -> dict[str, Any]:
        assert name == "jazn_generate_visible_reply"
        assert request_id == "synthetic-request"
        calls.append(str(args["message"]))
        return {
            "content": [{"type": "text", "text": "CANARY_RESULT"}],
            "structuredContent": {"ok": True, "action": "display_exact",
                                  "final_visible_text": "CANARY_RESULT"},
            "isError": False,
        }

    def server() -> JaznMcpServer:
        instance = JaznMcpServer(root=root, token="synthetic-token")
        monkeypatch.setattr(instance, "_dispatch", dispatch)
        return instance

    args = {"message": "synthetic message", "request_id": "synthetic-request"}
    if explicit_key:
        args["idempotency_key"] = "synthetic-key"

    def invoke(instance: JaznMcpServer, subject: str) -> dict[str, Any]:
        return instance.call_tool("jazn_generate_visible_reply", args,
                                  meta={"authorization": "synthetic-token", "subject": subject})

    first = invoke(server(), "subject-A")
    assert first["isError"] is False
    second = invoke(server(), "subject-B")
    assert second["isError"] is True
    assert "idempotency_conflict" in repr(second)
    assert "CANARY_RESULT" not in repr(second)
    same = invoke(server(), "subject-A")
    assert same["isError"] is False
    assert same["structuredContent"]["final_visible_text"] == "CANARY_RESULT"
    assert calls == ["synthetic message"]
