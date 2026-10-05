# Persistent Remote MCP Operations — v16.3.25.5.107

## Scope

This runbook closes the operational gap between a repository that *contains*
remote MCP code and a deployment that remains usable when a ChatGPT-local
executor disappears. The target topology is:

```text
ChatGPT custom MCP app
        |
        | HTTPS /mcp
        v
public edge / outbound tunnel
        |
        v
Jaźń MCP gateway
        |
        | loopback only
        v
persistent Jaźń daemon <-> runtime supervisor
```

The gateway, supervisor and local CLI remain clients/operators of one runtime.

## Protocol and auth corrections

MCP 2026-07-28 uses `server/discover` for the modern era and canonical
`tools/list` / `tools/call` methods. Do not generate non-standard
`mcp/list-tools` or `mcp/invoke` aliases.

Public non-loopback ingress stays OAuth-protected. The deployment code does not
downgrade production auth to a static bearer token and never writes credentials
into argv, package metadata or Git.

## Production readiness gate

Before the gateway is executed, deployment must verify:

- `ok=true`;
- `daemon_reachable=true`;
- `system_fully_ready=true`;
- `conversation_ready=true`;
- `activation_truth_gate_eligible=true`;
- exact `runtime_version == PACKAGE_VERSION_FULL`;
- non-empty daemon/runtime instance id.

Reachability alone is not readiness.

## Supervisor ownership

Production deployment requires the canonical runtime supervisor by default.
Reuse is accepted only when all three are true:

- supervisor active;
- process identity confirmed;
- heartbeat lease fresh.

If no verified supervisor exists, deployment starts `run.py supervisor-run`
and waits boundedly for lease evidence. `JAZN_MCP_REQUIRE_SUPERVISOR=0` is
permitted only when an external service manager provides equivalent recovery.

## Liveness vs readiness

- `/healthz`: gateway liveness;
- `/readyz`: runtime/gateway readiness.

Do not use readiness as proof of an accepted visible turn. ChatGPT must still
observe the current message's full Jaźń toolset, call the runtime exactly once,
resume the same request after ambiguous transport, and accept final
`display_exact`.

## Cloudflare Tunnel

The supplied Compose example uses outbound-only `cloudflared`. The token is an
operator secret and is intentionally not represented in repository manifests.
No inbound router port is required for this topology.

The tunnel must forward the public hostname to the gateway service on port 8080.
The daemon port 8787 remains loopback-private.

## Secure MCP Tunnel

Secure MCP Tunnel remains an alternative private transport, not a fallback that
the repository can activate by itself. Its runtime API key/tunnel association
are external deployment evidence. Do not put those credentials in SYSTEM ZIP,
source control or Jaźń memory.

## Failure injection / acceptance matrix

PASS requires all of the following:

1. cold deployment reaches strict runtime readiness and supervisor lease;
2. kill/restart the daemon while keeping gateway + supervisor alive: supervisor
   recovers it and `/readyz` returns to ready without creating duplicate turns;
3. stop the tunnel: local runtime stays healthy; restore tunnel and reuse the same
   daemon/runtime identity;
4. feed stale/mismatched runtime version: deployment refuses exposure;
5. feed reachable-but-`conversation_ready=false`: deployment refuses exposure;
6. remove supervisor heartbeat/identity: production startup refuses exposure;
7. simulate ambiguous transport after submit: only resume/poll the original
   request id; never resubmit the user message;
8. final visible response remains blocked unless accepted finalization returns
   `action=display_exact`.

## Rollout

1. build/test branch;
2. deploy to a non-production hostname;
3. verify `/healthz` and `/readyz` separately;
4. verify OAuth discovery/token validation;
5. connect a ChatGPT custom MCP app;
6. verify `jazn_status` plus full current-message toolset;
7. run one turn through generate/resume/finalize;
8. perform daemon and tunnel failure injection;
9. only then move the stable hostname.

## Rollback

Rollback is release-based, not state fabrication:

1. stop public ingress;
2. preserve mutable `workspace_runtime`/memory according to existing backup rules;
3. deploy the previous verified SYSTEM/container tag;
4. run canonical status/doctor/package gates;
5. restore ingress only after readiness and supervisor evidence pass.

Never roll back by editing `PACKAGE_INTEGRITY_MANIFEST.json`,
`SOURCE_PROVENANCE.json`, active markers or runtime version strings by hand.

## Truth boundary

This runbook proves deployability and resilience properties only when its tests
and external deployment checks pass. It cannot prove that a particular ChatGPT
conversation has the app selected/callable, and it cannot authorize Jaźń voice
without accepted per-turn finalization.
