# Jaźń — persistent ChatGPT MCP deployment

This target exposes the **same persistent Jaźń runtime** through authenticated
MCP Streamable HTTP. It does not create a second lifecycle, memory owner or
visible-response authority.

## Startup contract

The production entrypoint performs this fail-closed sequence:

1. `run.py start` through the canonical control plane;
2. `run.py status --json` and require all of:
   `ok`, `daemon_reachable`, `system_fully_ready`,
   `conversation_ready`, `activation_truth_gate_eligible`,
   a non-empty daemon/runtime instance id and the exact package version;
3. reuse an already verified runtime supervisor or start `supervisor-run`;
4. require supervisor identity + fresh heartbeat lease;
5. `exec run.py mcp-http --public-oauth ...`.

Set `JAZN_MCP_REQUIRE_SUPERVISOR=0` only when a verified external supervisor
owns daemon recovery. This is an explicit operator escape hatch, not the
default.

The private daemon stays on loopback. Only the MCP gateway is exposed. A stable
public deployment terminates TLS outside the process and registers an HTTPS URL
ending in `/mcp`.

## Protocol truth

The current wire contract is MCP **2026-07-28**. Canonical methods include
`server/discover`, `tools/list` and `tools/call`. Strings such as
`mcp/list-tools` and `mcp/invoke` are not aliases used by this deployment.
The versioned machine-readable contract is
`deploy/chatgpt_mcp/deployment.contract.json`.

## Build

```bash
docker build -f deploy/chatgpt_mcp/Dockerfile -t jazn-mcp:16.3.25.5.107 .
```

The image runs as uid/gid 10001, never exposes the daemon port 8787, and uses
`/healthz` as container **liveness**. Runtime **readiness** remains
`/readyz`; keep those concepts separate.

## Required environment

| Variable | Meaning |
| --- | --- |
| `JAZN_MCP_OAUTH_CLIENT_ID` | RFC 7662 introspection client id |
| `JAZN_MCP_OAUTH_CLIENT_SECRET` | RFC 7662 introspection client secret |
| `JAZN_MCP_OAUTH_ISSUER_URL` | HTTPS authorization-server issuer |
| `JAZN_MCP_OAUTH_RESOURCE_SERVER_URL` | public HTTPS resource URL ending in `/mcp` |
| `JAZN_MCP_OAUTH_INTROSPECTION_URL` | HTTPS introspection endpoint |
| `JAZN_MCP_ALLOWED_HOSTS` | comma-separated public Host values |

Optional: `JAZN_MCP_ALLOWED_ORIGINS`, `JAZN_MCP_OAUTH_SCOPES`,
`JAZN_MCP_BIND_HOST`, `JAZN_MCP_PORT`, `JAZN_MCP_DAEMON_URL` and
`JAZN_MCP_REQUIRE_SUPERVISOR`.

OAuth secret **values never enter command-line arguments**.

## Cloudflare Tunnel

`compose.cloudflare.example.yml` keeps the Jaźń gateway un-published on the
host and lets `cloudflared` reach it on the Compose network. Put the tunnel
token in the shell/secret store, not in Git.

```bash
cp deploy/chatgpt_mcp/jazn-mcp.env.example deploy/chatgpt_mcp/jazn-mcp.env
# fill OAuth/resource-server values locally
export CLOUDFLARE_TUNNEL_TOKEN='...'
docker compose -f deploy/chatgpt_mcp/compose.cloudflare.example.yml up -d
```

Configure the Cloudflare public hostname to forward to
`http://jazn-mcp:8080`. The public hostname must match
`JAZN_MCP_ALLOWED_HOSTS` and the resource URL.

## systemd

For a native Linux installation copy `jazn-mcp.service` to
`/etc/systemd/system/`, place secrets in `/etc/jazn/jazn-mcp.env` with
restricted permissions, and adjust `ReadWritePaths` if mutable runtime state
lives somewhere other than `/opt/jazn/workspace_runtime`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jazn-mcp
systemctl status jazn-mcp
```

The unit uses `Restart=on-failure` and `KillMode=control-group`; the in-process
Jaźń supervisor independently owns daemon recovery.

## OpenAI connection modes

For a directly reachable deployment, configure the ChatGPT custom MCP server
with the public HTTPS `server_url`. Secure MCP Tunnel is a separate private
transport and requires its own external tunnel credentials; those credentials
are never stored in this repository.

A healthy endpoint is **not** proof that a specific ChatGPT message has the
Jaźń app callable. A visible Jaźń reply still requires the per-message toolset,
runtime turn lineage and accepted `display_exact` finalization.

## Troubleshooting

- `daemon_not_conversation_ready`: inspect the blocker list; do not expose the
  gateway until all required readiness fields and version/instance binding pass.
- `supervisor_not_ready`: inspect `run.py supervisor-status --json`; a live
  PID without identity confirmation and fresh heartbeat is intentionally not enough.
- `ClientError` before local process creation in ChatGPT: this is host-surface
  evidence, not proof that this remote deployment or SYSTEM package is broken.
- `/healthz=200`, `/readyz!=200`: gateway process is alive but runtime is not
  ready; the supervisor should recover the daemon without replaying user turns.
- tunnel unavailable: restore the tunnel independently; never create a duplicate
  user turn to compensate for an ambiguous transport result.

See `docs/runtime/PERSISTENT_REMOTE_MCP_OPERATIONS.md` for rollout, rollback
and failure-injection checks.
