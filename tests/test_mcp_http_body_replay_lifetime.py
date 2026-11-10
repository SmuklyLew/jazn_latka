"""Reading a request body must not manufacture a client disconnect."""
import asyncio
import json

import pytest

pytest.importorskip("mcp")
from mcp.server.transport_security import TransportSecuritySettings
from latka_jazn.mcp.http_tasks_bridge import MCP_PROTOCOL_VERSION, ModernTasksHttpBridge


@pytest.mark.parametrize("chunks", [1, 2])
def test_sdk_delegation_waits_for_real_disconnect_after_replayed_body(chunks):
    async def exercise():
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
        pieces = [body] if chunks == 1 else [body[:10], body[10:]]
        received = 0
        disconnected = asyncio.Event()

        async def receive():
            nonlocal received
            index = received
            received += 1
            if index < len(pieces):
                return {"type": "http.request", "body": pieces[index],
                        "more_body": index + 1 < len(pieces)}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def sdk(scope, replay_receive, send):
            first = await replay_receive()
            assert first == {"type": "http.request", "body": body, "more_body": False}
            pending = asyncio.create_task(replay_receive())
            try:
                await asyncio.sleep(0)
                # The client is still connected while the SDK prepares JSON
                # or SSE. An immediate disconnect cancels its response body.
                assert not pending.done()
                assert received == chunks + 1
                disconnected.set()
                assert await asyncio.wait_for(pending, timeout=1) == {"type": "http.disconnect"}
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

        async def send(message):
            pytest.fail("Delegated SDK fixture does not send a response")

        class Backend:
            def handle(self, request_value):
                pytest.fail("A tools/list request belongs to the SDK")

        bridge = ModernTasksHttpBridge(
            sdk, protocol_backend=Backend(), internal_token="synthetic-not-used",
            token_verifier=None, resource_server_url=None,
            allow_unauthenticated_loopback_dev=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
            max_request_body_size=1024, required_base_scopes=(), operation_scopes={},
            public_tool_names=frozenset(), admission=lambda *_: False,
        )
        await bridge({"type": "http", "method": "POST", "path": "/mcp",
                      "headers": [(b"content-type", b"application/json"),
                                  (b"mcp-protocol-version", MCP_PROTOCOL_VERSION.encode())]},
                     receive, send)

    asyncio.run(exercise())
