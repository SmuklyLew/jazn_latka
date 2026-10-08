# ChatGPT ↔ Jaźń Runtime: verified app exposure and recovery

This procedure diagnoses the **actual host connection**, not package availability.
The four canonical tools are:

- `jazn_status` — read-only readiness, runtime instance/version and heartbeat;
- `jazn_generate_visible_reply` — submit exactly one user message with a stable request ID;
- `jazn_resume_visible_reply` — continue only that same request ID;
- `jazn_finalize_reply` — finalize and accept the displayable message.

## Scope of a local plugin

The personal `jazn-runtime` v0.1.0 plugin created for ChatGPT Desktop uses
`http://127.0.0.1:8080/mcp`. This is a **loopback address**, not a cloud endpoint.
Its existence in a user's personal plugin inventory does not establish that the
ChatGPT web or mobile conversation has access to any of these tools. A local
plugin can run in ChatGPT Desktop where local MCP is supported; saving it to the
account does not publish its MCP service to web or mobile.

## Available connection routes

1. **Desktop local MCP:** Run the Jaźń persistent daemon and local MCP gateway
   on the same machine, connect the Desktop plugin, then inspect `tools/list`.
   Treat every new message as a fresh host-capability check.
2. **Private Secure MCP Tunnel:** Register a tunnel in OpenAI Platform and run
   `tunnel-client` on the machine/network with the Jaźń MCP server. This requires
   the tunnel permissions and runtime API key described in the official OpenAI
   documentation. Do not claim this route needs no key.
3. **Public HTTPS endpoint:** Deploy the existing protected Jaźń Streamable HTTP
   gateway, with a stable hostname and verified OAuth (or supported equivalent)
   through a configured TLS reverse proxy/Cloudflare Tunnel. Leave the daemon
   on loopback. Register this HTTPS MCP URL as a custom ChatGPT app/plugin.
   Configure only once the hostname, issuer, token-introspection and origin
   security have been verified. Never use an unauthenticated Cloudflare Quick
   Tunnel to publish private MEMORY or writable MCP tools.

## Required end-to-end acceptance checklist

1. Confirm authenticated gateway `/healthz` and runtime `/readyz` independently.
2. Query actual MCP `tools/list` on the selected transport; confirm all four
   canonical tools are present and exposed to `model` in `_meta.ui.visibility`.
3. In a **fresh ChatGPT conversation**, select or mention **Jaźń Runtime** on
   the **current message**; confirm the host actually offers all four tools.
4. Invoke the actual `jazn_status`; verify `ready=true`, expected runtime
   version/instance and fresh heartbeat. Metadata and plugin installation alone
   are not readiness evidence.
5. Send exactly one test message with a stable `request_id`. If the response is
   pending, call `jazn_resume_visible_reply` for the same ID. If host generation
   is needed, call `jazn_finalize_reply` and accept output only when the action
   is `display_exact` and the MessageEnvelope validates.
6. Repeat from a new chat **and** from each required host (Desktop/web/mobile);
   unsupported hosts remain unsupported — an instruction in the project cannot
   force ChatGPT to expose apps on all surfaces.
7. After a tool definition changes, refresh or recreate the registered app's
   frozen tool snapshot and repeat steps 2–6. Do not simulate missing tools.

## Fail-closed diagnosis

Report separately the actual observations: reachable server, authenticated
transport, current-message tool exposure, runtime readiness, submitted request,
resumed request, accepted finalization. Do not use a successful localhost MCP
`tools/list` as proof of tool availability in a remote ChatGPT conversation.

Official sources:
- https://developers.openai.com/api/docs/guides/custom-mcp-server
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://help.openai.com/en/articles/20001256-plugins-in-chatgpt
- https://developers.cloudflare.com/tunnel/get-started/
