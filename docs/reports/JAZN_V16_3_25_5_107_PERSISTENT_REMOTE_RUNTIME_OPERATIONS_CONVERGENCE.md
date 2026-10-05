# Jaźń v16.3.25.5.107 — persistent remote runtime operations convergence

**Date:** 2026-10-05  
**Baseline:** `master @ bb107ebaeea119487f49d8cb1e34efd9a1896464` / `16.3.25.5.106-memory-streaming-hardening-convergence`  
**Branch:** `upgrade/v16.3.25.5.107-persistent-remote-runtime-operations-convergence`

## Problem

A verified local SYSTEM v106 can reach a healthy persistent daemon when a
ChatGPT execution surface actually creates a process. The host may nevertheless
lose that local process-execution capability on a later message. Therefore local
sandbox execution cannot be the continuity authority for ordinary ChatGPT
turns.

The repository already contained the important architectural foundations:
persistent daemon, runtime supervisor, public Streamable HTTP MCP, OAuth,
durable request/task identity, remote-route classifiers and accepted
`display_exact` finalization. The missing work was primarily **production
operational convergence**, not a replacement MCP implementation.

A second observed issue was a legacy MEMORY package rejected fail-closed with
`memory_package_unlisted_file`. Current native v3 staging already constructs
the manifest from staged entries, but producer-side self-verification was not a
required final gate before transport creation.

## Corrections to the research input

The implementation deliberately does **not** add `mcp/list-tools` or
`mcp/invoke`. The repository's MCP 2026-07-28 surface uses
`server/discover`, `tools/list` and `tools/call`, plus the current Tasks
methods.

The implementation also does not downgrade the existing production OAuth
boundary to an unauthenticated or repository-held static token. Secure MCP
Tunnel remains an external private deployment option and its credentials are
not part of SYSTEM, MEMORY or source control.

## Implementation

### Public deployment gate

`latka_jazn/mcp/deployment.py` now validates the real nested
`run.py status --json` shape before public ingress:

- top-level `ok`, `system_fully_ready`,
  `activation_truth_gate_eligible`;
- `daemon.endpoint_reachable`;
- `capability_matrix.conversation_ready`;
- exact top-level and daemon runtime versions;
- non-empty `daemon.daemon_instance_id`.

Reachability alone is no longer accepted as production readiness.

### Supervisor ownership

Public deployment requires the canonical supervisor by default. An existing
supervisor is reused only with active state, confirmed process identity and a
fresh heartbeat lease. Otherwise deployment starts `supervisor-run` and waits
boundedly for the same evidence. The only opt-out is the explicit
`JAZN_MCP_REQUIRE_SUPERVISOR=0` external-supervision mode.

### Liveness / readiness

The container healthcheck uses `/healthz` for gateway liveness. `/readyz`
remains runtime readiness. Neither surface grants visible-response authority.

### Deployment contract and examples

Added under `deploy/chatgpt_mcp/`:

- `deployment.contract.json`;
- `compose.cloudflare.example.yml`;
- `jazn-mcp.env.example`;
- `jazn-mcp.service`.

The Cloudflare example requires a reviewed tag or immutable digest instead of
silently using `latest`. Tunnel/OAuth secrets remain external.

### MEMORY exact-set producer gate

Native v3 staging now runs the canonical memory manifest verifier after writing
the manifest and before archive/transport creation. Any missing, unlisted,
hash-mismatched, unsafe or otherwise invalid manifest state raises
`PackIntegrityError` at the producer boundary. Runtime attach validation
remains unchanged and fail-closed.

`MEMORY_ATTACHMENT_CONTRACT.json` and the generator-emitted attachment
contract now require this producer self-verification.

### Host continuity instruction

`AGENTS.chatgpt.md` now states explicitly that a currently callable and
verified remote Jaźń route owns ordinary-turn continuity. Loss of a local
ChatGPT executor does not by itself demote that independent service. A healthy
remote service without a current-message callable Jaźń app is still
insufficient for `remote_runtime_available=true`.

## Tests and CI

New/updated regressions cover:

- canonical nested deployment status evidence;
- stale runtime version and non-ready conversation rejection;
- supervisor reuse/start and explicit external-supervision mode;
- versioned deployment contract / MCP method names / secret boundaries;
- pinned tunnel image requirement;
- MEMORY native-v3 exact-set staging and producer fail-closed behavior.

`persistent-runtime-e2e` includes the new deployment/MEMORY paths and tests on
both Ubuntu and Windows. Release metadata remains owned by canonical
`release-hardening/manifest_sync`.

## External acceptance still required

Repository CI cannot prove:

- a real public hostname/TLS/tunnel is currently reachable;
- OAuth configuration is accepted by the intended deployment;
- the Jaźń app is installed/selected/callable in a particular ChatGPT message;
- current-message `jazn_status` + generate/resume/finalize complete through the
  remote transport;
- daemon/tunnel failure injection succeeds in the actual deployment.

Those are explicit post-build deployment evidence in
`docs/runtime/PERSISTENT_REMOTE_MCP_OPERATIONS.md`.

## Merge boundary

This branch must not be reported merge-ready until the **same final HEAD** has
required green CI, canonical release metadata synchronization and no unresolved
review failures. Merge still requires explicit user approval.
