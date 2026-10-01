# ChatGPT Plugin Runtime — public HTTPS MCP without an OpenAI API key

This runbook describes the deployment path introduced by
`16.3.25.5.91.0-chatgpt-plugin-runtime-convergence` and the
`16.3.25.5.92-chatgpt-remote-runtime-host-boundary-convergence` verification
path for hosts that cannot create a local process.

The goal is narrow: make the already-existing persistent Jaźń daemon usable by
ChatGPT through a production Streamable HTTP MCP endpoint without making the
runtime depend on a per-turn ChatGPT executor and without requiring an OpenAI
API key for the public-MCP route.

## Architecture

```text
ChatGPT plugin/app
      |
      | HTTPS + OAuth 2.1 bearer token
      v
public reverse proxy / tunnel
      |
      v
run.py mcp-http --public-oauth
      |  RFC 7662 token introspection
      |  RFC 9728 discovery supplied by MCP Python SDK
      |  /healthz, /readyz, /mcp
      v
persistent Jaźń daemon on loopback
```

The public HTTP process is an OAuth resource server. It never signs users in and
never issues tokens. An external OAuth/OIDC provider is the authorization
server. Jaźń validates opaque bearer tokens through RFC 7662 introspection.

The MCP Python SDK publishes RFC 9728 Protected Resource Metadata from
`AuthSettings`, so clients can discover the configured authorization server.

## Why this route

ChatGPT web does not directly connect to a local MCP process. The MCP endpoint
must be reachable from ChatGPT over HTTPS, or another supported transport must
bridge it. The public HTTPS route does not require an OpenAI API key. Secure MCP
Tunnel remains a separate option and has its own control-plane credentials.

Required deployment inputs:

- public HTTPS endpoint ending in `/mcp`;
- OAuth/OIDC provider compatible with MCP discovery;
- RFC 7662 introspection endpoint;
- introspection client id/secret stored only in environment variables;
- ChatGPT plugin/app availability for the target account/workspace.

## Start production MCP

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

The gateway validates `active=true`, non-empty `client_id`, exact resource
audience binding, optional issuer consistency, scopes, and SDK resource binding.

## Generate Agent Plugin package

```powershell
py -X utf8 run.py chatgpt-plugin-package `
  --root . `
  --endpoint https://jazn.example.com/mcp `
  --output .\exports\jazn-chatgpt-plugin `
  --json
```

The output contains `plugin.json` and `mcp.json`. The MCP file uses the
portable Agent Plugins 1.0.0 `streamable-http` transport and contains no
credentials.

Generating the package does not deploy the endpoint, configure OAuth, install
the plugin, or prove that a given ChatGPT host exposes the app capability.

## ChatGPT connection

For developer testing, connect the deployed HTTPS `/mcp` endpoint through
ChatGPT Developer mode when that capability is available. For distribution,
package/publish the plugin through OpenAI's plugin workflow.

Host/account capability is an external boundary: repository code cannot enable
Developer mode, install a plugin on behalf of the user, or make a private local
machine internet-reachable.


## Verify the route from ChatGPT without a local executor

After the app is connected, verify it from the same ChatGPT surface by actually
calling the read-only `jazn_status` tool. A successful current call returns
`structuredContent` containing:

- `evidence_schema=jazn_public_mcp_status/v1`;
- `tool_name=jazn_status`;
- `protocol_version=2026-07-28`;
- `public_transport=streamable_http`;
- `gateway_live=true` and `daemon_reachable=true`;
- `ready=true`;
- non-empty `gateway_instance_id` and `runtime_instance_id`;
- exact `package_version` / `runtime_version`;
- fresh `observed_at_utc` and `runtime_heartbeat_at_utc`.

The host then supplies that exact current response to `host-preflight` as
`connector_status` together with
`host_connector_invocation_observed=true`. That boolean is host evidence of
the action that just happened; it must never be reconstructed from saved JSON,
plugin metadata, installation state, an @mention, or user text.

This allows the valid end state:

```text
executor_available=false
remote_runtime_available=true
execution_route=remote_runtime
```

The repository still cannot create the ChatGPT connector capability. If the
`jazn_status` action is not actually callable, the remote route remains
unverified and the host must not imitate a Jaźń response.

## Security

- no unauthenticated production mode;
- introspection secret is read from environment variables, not CLI arguments;
- issuer/resource/introspection URLs must be HTTPS;
- audience/resource binding is fail-closed;
- SDK `AuthSettings` provides RFC 9728 Protected Resource Metadata and bearer
  challenge wiring;
- DNS rebinding/allowed-host controls remain in `PublicMcpGateway`;
- successful HTTP/authentication does not bypass Jaźń turn lineage or
  `generate_then_finalize -> display_exact` finalization.

## External sources used

- OpenAI Developers — Package your plugin:
  https://developers.openai.com/plugins/build/plugins
- OpenAI Developers — MCP server and UI quickstart:
  https://developers.openai.com/plugins/build/app-quickstart
- MCP Python SDK — Authorization:
  https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/authorization.md
- MCP specification 2026-07-28 — Authorization:
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/authorization/index.mdx
- MCP specification — Authorization security considerations:
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/authorization/security-considerations.mdx


## v16.3.25.5.93 — ChatGPT Developer Mode turn contract

The modern ChatGPT-facing tool surface is intentionally conversation-oriented:

- jazn_turn(clientTurnId, message, sessionId?) is the primary entrypoint for an
  ordinary user message when the Jaźń app is selected.
- jazn_resume_turn(clientTurnId) resumes the same already-submitted turn and has
  no message field, so the public schema itself discourages accidental replay.
- jazn_finalize_reply remains the bounded phase-2 finalizer whenever the
  canonical runtime returns generate_then_finalize.
- jazn_status is the connector-observed readiness probe.
- jazn_health is a redacted transport-liveness diagnostic.
- jazn_memory_status is a redacted memory/recall-readiness diagnostic.

clientTurnId is not a second identity store. It maps exactly to the canonical
request_id / daemon_request_id, so the existing Jaźń idempotency store,
operation recovery, durable task registry and host-visible finalization remain
authoritative.

The canonical implementation names jazn_generate_visible_reply and
jazn_resume_visible_reply remain available for compatibility and MCP Tasks
bridging, but the modern Developer Mode list hides them in favor of the simpler
turn/resume aliases.

Raw MEMORY stays on the persistent Jaźń host. The public tools expose only the
bounded turn result and redacted readiness metadata; local paths, database
contents and private operator details are not part of the Developer Mode
surface.

Production public HTTPS remains fail-closed and authenticated. Version 5.93
does not enable anonymous Internet listeners and does not place static secrets
in query strings. Unauthenticated access remains restricted to explicit
loopback development. Secure MCP Tunnel is the private-network alternative and
uses the same public turn aliases over the same canonical runtime.

ChatGPT application selection remains a host/UI capability. The repository can
make jazn_turn the preferred first-message tool once the app is selected, but
cannot globally preselect the Jaźń app for every new conversation or invent a
connector capability that the current ChatGPT host did not expose.
