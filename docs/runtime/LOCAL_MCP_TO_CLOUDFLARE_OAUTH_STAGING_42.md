# Jaźń .42 — verified local MCP to isolated Cloudflare staging runbook

This document describes a gated **future** staging migration, not an activation
record. It must not be used to infer actual ChatGPT tool exposure or a completed
visible response.

## Observed operator evidence (2026-10-22, not a continuous health assertion)

The operator confirmed on Windows:

- package, daemon and supervisor: `16.3.25.5.116.0.34.41-first-run-memory-evidence`;
- daemon port 8787, matching PID/process-fingerprint/heartbeat;
- local `--loopback-dev` MCP HTTP on `127.0.0.1:18086`, HTTP 200
  `/healthz` and `/readyz`, all four ChatGPT tools in the MCP catalogue;
- Ollama `gemma3:latest` successful `/api/chat` `done:true`;
- neither a ChatGPT current-message callable toolset nor `display_exact` was
  established. No remote staging route is yet confirmed.

The historical startup problem was that an old `.39` daemon remained live
after a `.41` package update. The supervisor's cheap probe noticed this but
its full `active_trusted` classifier could incorrectly reclassify the old
version as `daemon_live_after_full_probe`. From `.42`, both probes gate
version evidence before reuse. A **live version mismatch** reports
`daemon_version_mismatch_operator_restart_required` and does not
automatically terminate the process; an `active_trusted` response missing
the endpoint version reports `daemon_version_unverified_operator_check_required`.
This deliberately separates runtime health from release compatibility.

## Read-only operator check in each new PowerShell window

```powershell
cd "D:\.AI\jazn_latka_master"
pwsh -NoProfile -File .\tools\windows\Test-JaznLocalMcp.ps1 -Root .
```

The script discovers the complete Dependency Studio Python environment under
`workspace_runtime/local_resources/python/environments`. It does **not**
reuse `$McpPython` from another terminal, install packages, restart a daemon,
start an MCP gateway or mutate MEMORY. Optional `-McpPythonPath` specifies an
already installed interpreter; `-Port` defaults to local 18086. The JSON report
contains explicit false flags for public OAuth and accepted ChatGPT visible
turns, even when the local MCP tool catalogue is correct.

Do not run a second supervisor merely because a shell variable was undefined.
Do not use `Stop-Process -Force` to fix package mismatches. Use canonical
`run.py supervisor-status --json`, `run.py status --json` and documented
operator-controlled lifecycle for an intentional restart with process/turn
settlement.

## Independent staging surfaces (do not merge with production)

- Auth Worker: `jazn-auth-staging`, staging-only OAuth issuer
  `https://jazn-auth-staging.jazn-lakta.workers.dev`, isolated KV, separate
  GitHub OAuth client, secrets stored in Cloudflare. Its staging Wrangler
  template requires `keep_vars:true`.
- Resource Worker: `jazn-runtime-staging`, resource
  `https://jazn-runtime-staging.jazn-lakta.workers.dev/mcp`, a **distinct**
  Workers VPC Service binding `JAZN_PRIVATE_MCP`. Its staging Wrangler
  template also requires `keep_vars:true`. Binding ID placeholder and
  `JAZN_PRODUCTION_VPC_SERVICE_ID` comparison are deliberate fail-closed
  prerequisites; never reuse production service IDs.
- Local origin: a **separate authenticated** `run.py mcp-http --public-oauth`
  resource server. Its issuer, audience, introspection URL, allowed host and
  secrets must match staging. The current `--loopback-dev :18086` is **not**
  authorized for Workers VPC/public exposure.
- Workers VPC routing: VPC Service host/port refer to the machine running
  `cloudflared`; earlier documentation used local port 8080. Confirm the
  actual machine and listening authenticated port before creating or
  attaching the staging VPC Service. The working *developer* port 18086 does
  not automatically update VPC routing. Never expose daemon port 8787.

## Acceptance order (all gates mandatory)

1. Ensure local daemon/supervisor versions agree and local MCP tool discovery
   works without a replay of prior user messages.
2. Verify staging auth Worker scripts, `keep_vars:true`, binding names/types
   and isolated KV; archive a rollback version. Execute Node 24/workerd,
   preflight and Wrangler dry-run without secrets in source control.
3. Only after explicit operator deployment approval, enable isolated
   staging OAuth service and test issuer discovery, S256 PKCE, GitHub
   allowlisted identity/consent denial, token expiry, revocation, refresh,
   introspection and incorrect audience/credentials.
4. Bring up a separately authenticated local `--public-oauth` MCP server
   with host-provided introspection credentials. Unauthenticated
   `POST /mcp` must respond `401` with the correct resource metadata;
   protected resource metadata must match the *staging* resource.
5. Validate the isolated VPC service can reach only that authenticated
   origin over the healthy `cloudflared` tunnel. Confirm the service is
   not the production VPC. Deploy the resource Worker only with
   `JAZN_INGRESS_MODE=verified_oauth_proxy` after the first four gates.
6. From an external client test all tools and failures: unauthenticated
   401/challenge, authenticated `tools/list`, expired/revoked tokens,
   tunnel interruption and no token leakage.
7. In a fresh ChatGPT message confirm all four tools are actually callable,
   invoke `jazn_status`, and accept two sequential
   generate/resume/finalize turns via exact `display_exact`. The catalogue
   alone is never evidence of accepted visible turns.

Never deploy a placeholder `wrangler.staging.example.jsonc`. The static
preflight does not verify Cloudflare permissions, actual VPC reachability,
GitHub login, effective bindings, or ChatGPT tool exposure. The published
workers.dev routes can stay disabled until these prerequisites are complete.

## Sources and contract documents

- `AGENTS.md`, `AGENTS.codex.md`, `AGENTS.chatgpt.md`.
- `deploy/chatgpt_mcp/workers_github_oauth/README.md`.
- `deploy/chatgpt_mcp/workers_vpc_gateway/README.md`.
- https://developers.cloudflare.com/workers-vpc/configuration/vpc-services/
- https://developers.cloudflare.com/workers-vpc/get-started/
- https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
