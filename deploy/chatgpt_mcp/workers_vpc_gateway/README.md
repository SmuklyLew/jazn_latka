# Jaźń — free Cloudflare Worker / Workers VPC ingress (2026-10-14)

## Observed deployment (not proof of runnable MCP)

The operator's Cloudflare account has a registered Workers subdomain
`jazn-lakta.workers.dev`, a healthy tunnel named `jazn-runtime`, and a
private Workers VPC service named `jazn-runtime-mcp-private`. The service
targets the loopback TCP port 8080 *on the machine running cloudflared*.
The Worker named `jazn-runtime` is deployed and its workers.dev route enabled
with public previews disabled. Its private VPC binding is named
`JAZN_PRIVATE_MCP`.

Target HTTPS address, once end-to-end verification is possible:
`https://jazn-runtime.jazn-lakta.workers.dev/mcp`.

**This release is intentionally STAGING ONLY.** All requests to `/mcp` and
OAuth well-known paths return **503**. Nothing is forwarded to the private
server. `/healthz` describes the gateway as `mcp_available:false`; it does
not claim runtime or memory readiness. The existing local-only plugin's
`http://127.0.0.1:8080/mcp` descriptor is unchanged.

## Why this is fail-closed

This account has no Cloudflare DNS zones. A named Tunnel by itself does
not provide a public hostname. Cloudflare Workers instead supplies the
free `workers.dev` HTTPS address, and Workers VPC binds a *single* private
service through the existing Tunnel, limiting the reachability of the
upstream. Workers VPC is presently beta and its free use is not promised
indefinitely.

The configured origin uses `127.0.0.1:8080`. That address is interpreted
by **cloudflared**, not by ChatGPT or the Cloudflare edge. If cloudflared
runs in a different container / host than the Jaźń MCP server, change
the VPC Service target to an actually reachable private address **after
verifying topology**. Do not open public firewall or expose the daemon
port 8787.

## OAuth and required acceptance before enabling forwarding

The current Jaźń mcp-http code already implements `--public-oauth` with:
- `JAZN_MCP_OAUTH_ISSUER_URL`: issuer URL
- `JAZN_MCP_OAUTH_INTROSPECTION_URL`: RFC 7662 introspection endpoint
- `JAZN_MCP_OAUTH_CLIENT_ID` and `JAZN_MCP_OAUTH_CLIENT_SECRET` (secrets)
- `JAZN_MCP_OAUTH_RESOURCE_SERVER_URL`: the precise public HTTPS /mcp URL
- `JAZN_MCP_ALLOWED_HOSTS`: the Cloudflare hostname
- a verified reachable persistent daemon; `/readyz` not only `/healthz`.

Cloudflare Access is not currently enabled for this account, and no
separate authorization server, introspection credentials or OAuth client
registration were provided. Do not invent an issuer, automatically enroll
a paid service, or use an anonymous or static-token public MCP fallback.

A future production Worker may proxy only a strict list of MCP resource,
discovery and protocol paths to `env.JAZN_PRIVATE_MCP.fetch`; the private
Jaźń resource server must verify bearer tokens, scopes and issuer on *every*
request, advertise RFC 9728 resource metadata, and preserve session/turn
idempotency and accepted `display_exact`. The Worker must never treat
`Authorization: Bearer <anything>` as sufficient authentication itself.

Operator acceptance order:
1. Verify host-side cloudflared is running on the expected machine and
   **can reach** `http://127.0.0.1:8080/readyz` or the applicable container
   address; verify fresh daemon status and required MCP tools.
2. Select/enable a free standards-compatible OAuth authorization server
   with discovery, PKCE and RFC 7662 introspection; store credentials only
   in host secrets, never Git or plugin descriptors.
3. Run `run.py mcp-http --public-oauth` under the project's supervisor
   with correct resource URL, scopes and allowlisted Host.
4. Implement and review OAuth-preserving Worker forwarding as a **separate
   gated change**. Recheck scopes, HTTP methods, streaming, headers, and
   disable any request rewriting that breaks OAuth metadata/resource.
5. Verify from *outside* the private network: TLS and host, unauthenticated
   `/mcp` must respond 401 with the proper resource_metadata challenge,
   an authenticated `tools/list` must expose all four Jaźń tools, and
   a full generate/resume/finalize turn must end with `display_exact`.
6. Update the *remote* plugin only to this fully verified HTTPS endpoint;
   keep local plugin route separately available. Test app installation and
   callable tools in **a fresh ChatGPT message**, not just uploaded files.
7. Run fault-injection: expire OAuth tokens, break tunnel, restart client,
   fail stdout after commit; verify no duplicate finalizations or leakage.

## Test commands

```bash
node --test deploy/chatgpt_mcp/workers_vpc_gateway/worker.test.mjs
python -X utf8 -m pytest -q tests/test_chatgpt_plugin_package.py
python -X utf8 tools/chatgpt_mcp_connection_doctor.py --plugin-dir /path/to/exported/plugin
```

The HTTP staging test is complete only after a real external client can
retrieve `/healthz` (200, mcp_available=false) and `/mcp` (503). The
current ChatGPT host executor cannot resolve external DNS to verify this,
so dashboard API proofs alone must not be called end-to-end success.

## Official sources

- https://developers.cloudflare.com/workers-vpc/configuration/vpc-services/
- https://developers.cloudflare.com/workers-vpc/configuration/tunnel/
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/workers/configuration/multipart-upload-metadata/
- https://developers.openai.com/plugins/build/auth
