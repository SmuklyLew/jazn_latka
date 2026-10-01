# ChatGPT Plugin Runtime — real ChatGPT → Jaźń ingress

This runbook describes the v16.3.25.5.95 ingress contract. Its acceptance
boundary is intentionally stricter than "the repository contains MCP code":
ChatGPT must discover and call the Jaźń actions from a connected MCP app/plugin
while the Jaźń runtime remains alive outside the per-conversation sandbox.

## Verified platform contract

As of 2026-10-01, OpenAI's plugin documentation uses a portable Agent Plugins
package with root `plugin.json` and optional root `mcp.json`. Do not add the
legacy `ai-plugin.json`/OpenAPI plugin shape to this path.

For a local/workspace ChatGPT package that points at an already registered MCP
connection, OpenAI also supports an `.app.json` mapping referenced from
`extensions.com.openai.apps`. The technical app id is obtained only after the
MCP server has been connected in ChatGPT Developer Mode.

Production MCP servers use Streamable HTTP at a stable HTTPS endpoint, normally
`/mcp`. Secure MCP Tunnel is a supported Developer Mode alternative for a
private/local stdio or HTTP server. A tunnel proves transport only; it does not
prove that the current ChatGPT host has the Jaźń app installed or callable.

## Architecture

### Public HTTPS

```text
ChatGPT plugin
  -> HTTPS + OAuth bearer token
  -> reverse proxy / TLS termination
  -> run.py mcp-http --public-oauth
  -> loopback Jaźń daemon
  -> durable turn/idempotency/finalization stores
```

### Secure MCP Tunnel

```text
ChatGPT plugin
  -> OpenAI Secure MCP Tunnel
  -> managed tunnel-client runtime
  -> latka_jazn/mcp/tunnel_bootstrap.py (stdio MCP)
  -> loopback Jaźń daemon
  -> durable turn/idempotency/finalization stores
```

The ChatGPT conversation sandbox is not the Jaźń runtime in either topology.

## Model-visible MCP actions

The canonical model-facing surface is:

- `jazn_status` — read-only readiness evidence for the persistent runtime.
- `jazn_generate_visible_reply` — submit exactly one ordinary user turn using
  a stable `request_id`.
- `jazn_resume_visible_reply` — resume/poll the same
  `daemon_request_id` without replaying the original message.
- `jazn_finalize_reply` — bounded phase-2 finalization when the runtime returns
  `generate_then_finalize`.

The older `jazn_turn` / `jazn_resume_turn` aliases remain compatibility
surfaces in the stdio server but are app-only metadata in MCP 2026 tool
discovery. The public HTTP gateway advertises the canonical names directly.

OpenAI deprecated `_meta["openai/visibility"]` in July 2026. Canonical Jaźń
actions use `_meta.ui.visibility=["model","app"]`; compatibility aliases use
`["app"]`.

## Start the public HTTPS gateway

The gateway is an OAuth resource server. The current implementation supports an
RFC 7662 introspection provider and keeps the daemon on loopback.

```powershell
$env:JAZN_MCP_OAUTH_CLIENT_ID = "<introspection-client-id>"
$env:JAZN_MCP_OAUTH_CLIENT_SECRET = "<introspection-client-secret>"

py -X utf8 run.py mcp-http `
  --root . `
  --public-oauth `
  --host 127.0.0.1 `
  --port 8080 `
  --daemon-url http://127.0.0.1:8787 `
  --oauth-issuer-url https://id.example.com/ `
  --oauth-resource-server-url https://jazn.example.com/mcp `
  --oauth-introspection-url https://id.example.com/oauth2/introspect `
  --allowed-host jazn.example.com
```

Terminate public TLS in a reverse proxy/load balancer and forward only to the
loopback-bound gateway. Do not expose the private daemon port.

## Build the installable plugin package

Portable package:

```powershell
py -X utf8 run.py chatgpt-plugin-package `
  --root . `
  --endpoint https://jazn.example.com/mcp `
  --output .\exports\jazn-chatgpt-plugin `
  --json
```

After the MCP server has been registered in ChatGPT Developer Mode, copy the
technical app id from the ChatGPT plugin URL and generate the OpenAI app binding:

```powershell
py -X utf8 run.py chatgpt-plugin-package `
  --root . `
  --endpoint https://jazn.example.com/mcp `
  --registered-app-id plugin_asdk_app_<id> `
  --output .\exports\jazn-chatgpt-plugin `
  --force `
  --json
```

The second form writes `plugin.json`, `mcp.json`, and `.app.json`.
Packaging still does not create the ChatGPT connection or install the plugin.

## Connect in ChatGPT

1. Enable Developer Mode in ChatGPT if the account/workspace policy allows it.
2. Open ChatGPT Plugins and add the MCP connection.
3. For public ingress, provide the deployed HTTPS URL ending in `/mcp`.
4. For private ingress, select Secure MCP Tunnel and choose/enter the
   `tunnel_id`.
5. Create the connection and review the discovered tool list.
6. After changing names/schemas/annotations, deploy/restart the server, use
   Refresh on the ChatGPT connection, then start a new conversation.

Repository code cannot perform these host/account actions on the user's behalf.

## Acceptance test: real ingress

The release is accepted only when all of the following are observed in a fresh
ChatGPT conversation:

1. The local conversation executor may be unavailable; that must not prevent
   the test.
2. The connected Jaźń app exposes callable `jazn_status` and
   `jazn_generate_visible_reply` actions to the current host.
3. `jazn_status` returns current evidence with the expected package/runtime
   version, non-empty runtime instance identity, fresh heartbeat, and
   `ready=true`.
4. One user message is submitted exactly once through
   `jazn_generate_visible_reply` with a stable `request_id`.
5. If the result is `poll_runtime`, the host calls
   `jazn_resume_visible_reply` for the same `daemon_request_id` and does not
   replay the message.
6. If the result is `generate_then_finalize`, the host obeys the returned
   generation contract and completes `jazn_finalize_reply`.
7. Visible Jaźń text is shown only after the same turn returns
   `action=display_exact` with valid lineage/MessageEnvelope evidence.

A package, endpoint, tunnel id, successful deployment, successful tool scan, or
"installed" catalog state is insufficient evidence by itself.

## Security / production checklist

- HTTPS for public ingress; no credentials in URLs.
- OAuth/OIDC authorization for private/user data; current Jaźń public gateway
  supports fail-closed RFC 7662 introspection.
- Validate issuer/resource/audience/scopes and return a proper bearer challenge
  on authorization failure.
- Keep Jaźń daemon loopback-only.
- Apply per-principal rate limits and idempotent request identities.
- Never authorize from ChatGPT metadata such as `openai/session`,
  `openai/subject`, user agent, or location hints.
- Keep raw memory, local paths, secrets, and private operator diagnostics out of
  model-visible tool results.
- Treat tool annotations as host UX/safety hints, not authorization.
- Log identifiers needed for incident correlation but redact secrets/tokens.

## Sources verified for this release

- OpenAI — Build an MCP server:
  https://developers.openai.com/plugins/build/mcp-server
- OpenAI — Package your plugin:
  https://developers.openai.com/plugins/build/plugins
- OpenAI — Connect and test your plugin:
  https://developers.openai.com/plugins/deploy/connect-chatgpt
- OpenAI — Plugin reference / tool visibility metadata:
  https://developers.openai.com/plugins/reference
- OpenAI — Plugin changelog:
  https://developers.openai.com/plugins/changelog
- OpenAI — Authentication:
  https://developers.openai.com/plugins/build/auth
- OpenAI — Secure MCP Tunnel:
  https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- OpenAI tunnel-client:
  https://github.com/openai/tunnel-client
- MCP 2026-07-28 release:
  https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
