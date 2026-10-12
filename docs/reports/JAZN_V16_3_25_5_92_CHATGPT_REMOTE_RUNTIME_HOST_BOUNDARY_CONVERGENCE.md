# Jaźń v16.3.25.5.92 — ChatGPT remote-runtime host-boundary convergence

## Problem

The observed ChatGPT incident fails before Jaźń code can execute: a pre-spawn
host `ClientError` leaves local process creation unavailable. That condition is
outside repository control and must not be mislabeled as a bootstrap, ZIP,
Python dependency, or runtime-code failure.

The second blocker was operational: public MCP code existed, but ChatGPT needed
a concrete way to prove the remote route from the same host surface without
requiring a local executor or arbitrary HTTP probes.

## Implemented convergence

- Added `classify_public_connector_status_failover()`.
- `jazn_status` now emits the versioned `jazn_public_mcp_status/v1` evidence
  contract with protocol, gateway/runtime binding, versions and freshness data.
- `host-preflight` accepts that status only when the current host separately
  reports `host_connector_invocation_observed=true`.
- A copied/stale status, plugin-listing result, `installed` flag, URL or
  @mention cannot promote `remote_runtime`.
- Direct `/healthz` + `/readyz` evidence remains supported. The two public
  evidence modes are mutually exclusive.
- Host surface diagnostics now export a bounded `failure_stage` and source,
  distinguishing allocation/materialization/mount/spawn where evidence exists,
  while preserving filesystem/package/runtime as unknown/unverified for a
  process that never started.
- Version bumped to
  `16.3.25.5.92-chatgpt-remote-runtime-host-boundary-convergence`.

## Why this fixes the repository-controlled gap

A ChatGPT host with no local executor can now use an already connected Jaźń app
as the discovery path:

```text
ChatGPT -> actual jazn_status tool call
        -> fresh connector status contract
        -> host-preflight classifier
        -> remote_runtime
        -> jazn_generate_visible_reply / resume / finalize
        -> display_exact only after accepted finalization
```

No code path pretends that the SYSTEM ZIP can create a host executor. No route
is promoted from package metadata alone.

## Deployment boundary

This release cannot itself:

- provision ChatGPT's per-turn executor;
- create a public DNS/TLS endpoint;
- choose or operate an OAuth provider;
- install/enable the Jaźń app in a user's ChatGPT account;
- assert `host_connector_invocation_observed=true` without an actual tool call.

Those remain deployment/host capabilities.

## External references checked

- OpenAI Developers — MCP server and UI quickstart.
- OpenAI Developers — Authentication for MCP-backed plugins (OAuth 2.1,
  Protected Resource Metadata / PKCE / resource binding).
- OpenAI Developers — Connect and test your plugin.
- Model Context Protocol Python SDK v2 documentation and release line for MCP
  protocol revision 2026-07-28.

## Validation gates

The branch must pass the existing release gates plus the new connector-probe
regressions:

```bash
python -X utf8 -m compileall -q -x 'tests[\\/]archive[\\/]' latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp" --ignore=tests/archive
python -m pyright --project pyrightconfig.json
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
```

Because the current ChatGPT host may itself lack process creation, inability to
run those commands locally is not treated as a code result. GitHub Actions is
the independent execution surface for branch verification.
