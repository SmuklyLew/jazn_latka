"""Protocol-era contract for Studio MCP probe (offline, non-invasive)."""
from __future__ import annotations

import json
from tools.jazn_start_studio import StudioCore, mcp_request_meta


def test_mcp_2026_request_metadata():
    meta = mcp_request_meta()
    assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
    assert meta["io.modelcontextprotocol/clientCapabilities"] == {}
    info = meta["io.modelcontextprotocol/clientInfo"]
    assert info["name"] == "jazn-start-studio-probe"
    assert isinstance(info["version"], str)


def test_mcp_2026_discover_uses_metadata_and_no_conversation_call():
    meta = mcp_request_meta()
    request = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "server/discover",
        "params": {"_meta": meta},
    }
    blob = json.dumps(request)
    assert json.loads(blob)["method"] == "server/discover"
    assert "tools/call" not in blob
    assert "Authorization" not in blob


def test_mcp_receive_rejects_text_logging_on_stdout():
    import queue
    inbox: queue.Queue[str] = queue.Queue()
    inbox.put("startup complete\n")
    try:
        StudioCore._mcp_receive(inbox, 10, None, timeout=0.2)
    except RuntimeError as error:
        assert "Non-JSON" in str(error)
    else:
        raise AssertionError("stdio stdout accepted non-JSON log")
