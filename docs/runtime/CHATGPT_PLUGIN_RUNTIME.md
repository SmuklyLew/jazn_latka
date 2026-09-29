# ChatGPT Plugin Runtime — public HTTPS MCP without an OpenAI API key

This runbook describes the deployment path introduced by
`16.3.25.5.91.0-chatgpt-plugin-runtime-convergence`.

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
