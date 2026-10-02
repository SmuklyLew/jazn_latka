# Jaźń — persistent ChatGPT MCP container

This deployment target runs the **same Jaźń runtime and control plane** that are
used locally. It is not a second implementation of lifecycle, memory, turn
ownership or finalization.

The container entrypoint performs only this sequence:

1. `run.py start`;
2. `run.py status --json` and requires `ok=true` plus
   `daemon_reachable=true`;
3. `exec run.py mcp-http --public-oauth ...`.

The private daemon remains bound to loopback. Only the MCP gateway port is
exposed. Public TLS must be terminated by the deployment platform, reverse
proxy or load balancer, so the URL registered in ChatGPT is a stable HTTPS
endpoint ending in `/mcp`.

## Build

From the repository root:

```bash
docker build -f deploy/chatgpt_mcp/Dockerfile -t jazn-mcp:16.3.25.5.95.1 .
```

The root `.dockerignore` excludes private/mutable runtime state and common
secret files from the build context.

## Required environment

| Variable | Meaning |
| --- | --- |
| `JAZN_MCP_OAUTH_CLIENT_ID` | RFC 7662 introspection client id |
| `JAZN_MCP_OAUTH_CLIENT_SECRET` | RFC 7662 introspection client secret |
| `JAZN_MCP_OAUTH_ISSUER_URL` | HTTPS authorization-server issuer |
| `JAZN_MCP_OAUTH_RESOURCE_SERVER_URL` | Public HTTPS MCP resource URL, ending in `/mcp` |
| `JAZN_MCP_OAUTH_INTROSPECTION_URL` | HTTPS RFC 7662 introspection endpoint |
| `JAZN_MCP_ALLOWED_HOSTS` | Comma-separated public Host values accepted by the MCP transport-security layer |

Optional:

- `JAZN_MCP_ALLOWED_ORIGINS` — comma-separated browser origins when needed;
- `JAZN_MCP_OAUTH_SCOPES` — comma-separated scope override; otherwise the
  gateway uses the canonical Jaźń MCP scope set;
- `JAZN_MCP_BIND_HOST` / `JAZN_MCP_PORT` — defaults: `0.0.0.0:8080`;
- `JAZN_MCP_DAEMON_URL` — defaults to `http://127.0.0.1:8787` and is
  rejected if it is not loopback.

OAuth secret **values are never added to command-line arguments**.

## Example

```bash
docker run --rm \
  -p 8080:8080 \
  -v jazn-runtime:/opt/jazn/workspace_runtime \
  -e JAZN_MCP_OAUTH_CLIENT_ID \
  -e JAZN_MCP_OAUTH_CLIENT_SECRET \
  -e JAZN_MCP_OAUTH_ISSUER_URL=https://id.example.com/ \
  -e JAZN_MCP_OAUTH_RESOURCE_SERVER_URL=https://jazn.example.com/mcp \
  -e JAZN_MCP_OAUTH_INTROSPECTION_URL=https://id.example.com/oauth2/introspect \
  -e JAZN_MCP_ALLOWED_HOSTS=jazn.example.com \
  jazn-mcp:16.3.25.5.95.1
```

Do not publish port 8787. Put HTTPS/TLS in front of port 8080, then register the
resulting `https://.../mcp` endpoint in ChatGPT Developer Mode and inspect the
discovered tools. A healthy container still does **not** prove that a particular
ChatGPT conversation has the Jaźń app installed or callable; real host
acceptance remains a separate gate described in
`docs/runtime/CHATGPT_PLUGIN_RUNTIME.md`.
