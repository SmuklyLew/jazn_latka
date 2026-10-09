# Jaźń v16.3.25.5.115.12 — ChatGPT runtime activity freshness convergence

## Scope and observed defect

The prior model-visible `jazn_status` treated a reachable gateway, reachable
daemon, matching package version, non-empty instance ID and
`conversation_ready=true` as sufficient to set `ready=true`. It reported
`last_heartbeat_at_utc` but did not *itself* require the daemon heartbeat to
be fresh. A reachable endpoint with stale runtime activity could therefore
produce a misleading affirmative status prior to downstream host classification.

This release fixes that owner-level evidence gap. It does **not** assert that
the host always exposes the Jaźń MCP app or can create a local executor.

## Implementation

- `latka_jazn/mcp/tools/jazn_status.py` applies the existing
  `remote_runtime.observation_is_fresh` policy to the daemon's own
  `last_heartbeat_at_utc` using one UTC observation clock. This keeps the
  existing 120-second maximum age and 5-second future-skew tolerance.
- Readiness remains fail-closed when the heartbeat is absent, invalid, naive,
  too old or unreasonably in the future.
- The model-visible status now includes `runtime_heartbeat_fresh` and a
  redacted `runtime_activity` projection:
  - `ready`: observed gateway + daemon + capability + instance/version and
    fresh heartbeat all agree;
  - `stale`: gateway and daemon appear reachable with an instance ID, but
    no trustworthy fresh runtime heartbeat was provided;
  - `unready`: fresh heartbeat exists, but another readiness gate failed;
  - `unknown`: gateway or daemon reachability/instance binding is absent.
- The projection is *evidence about runtime activity*, never a proof of a
  successfully submitted user request or of accepted visible finalization.
  It does not disclose runtime paths, PIDs, secrets or private memory metadata.
- Existing `runtime_supervisor.py` continues to own supervisor state,
  process identity/fingerprint, atomic heartbeat/lease storage and recovery.
  No secondary supervisor, synthetic heartbeat or competing
  `runtime_activity.json` marker is created.
- The registered-MCP test fixture obtains a fresh clock for a live gateway
  observation instead of defaulting to a hard-coded old timestamp.
  The byte-exact pre-change active test is archived under `tests/archive/`.

## Canonical ChatGPT lifecycle (unchanged)

1. For every message, discover genuinely callable canonical Jaźń tools.
2. Prefer verified, fresh remote `jazn_status` + complete current-message
   toolset; only then bind the message **once**.
3. When no remote conversation-ready route exists before submit, allow at
   most one primary and one genuinely independent alternative local process
   probe. Pre-spawn `ClientError` establishes only that surface's execution
   failure; filesystem and ZIP remain **unknown**.
4. A successfully created host process may verify the SYSTEM ZIP's trusted
   size/hash/CRC/path-safety, materialize `CHATGPT_BOOTSTRAP.py`, and use
   canonical `main.py`/`run.py` preflight/start/live status. Never assume a
   Library `file_id` is an OS path or guess an ID for materialization.
5. Prefer warm/resume reuse for verified roots. Do not re-extract SYSTEM on
   each message. Optional MEMORY remains an independent capability.
6. After the submit boundary, never replay or switch routes on transport
   ambiguity: resume the same `request_id` and require accepted finalization
   with `action=display_exact` and valid `MessageEnvelope`.

The host cannot sample local heartbeat files while it has no filesystem
access. Persistent supervision occurs in the daemon/supervisor process; the
host obtains a redacted current observation through MCP when callable.

## Regression/CI acceptance

New active regression module:
`tests/test_chatgpt_runtime_activity_freshness_v11512.py`.

Test cases: live fresh heartbeat; missing/empty/invalid/naive timestamp;
expired timestamp; excessive future timestamp; unreachable daemon;
conversation capability not ready; mismatched runtime version; model-visible
redaction.

Existing `tests/test_chatgpt_registered_mcp_status_convergence.py` remains
active and expects fresh live timestamps. Its exact prior bytes were preserved
in the versioned archive.

Release acceptance requires, at minimum, the repository's release-hardening
workflow: metadata sync/idempotency, compileall, Pyright, deterministic
pytest on Linux, targeted Windows tests, pack-generator bundle check and
clean-checkout guards. A green CI conclusion must be checked on the **latest**
commit SHA, not inferred from the existence of a branch or an older run.
The SYSTEM ZIP is a deployable artifact, not proof of a running ChatGPT route.

## External primary sources

- OpenAI, *Add custom MCP server* (current-message selection/refresh of tools):
  https://developers.openai.com/api/docs/guides/custom-mcp-server
- OpenAI, *Plugin reference*, `_meta.ui.visibility`:
  https://developers.openai.com/plugins/reference
- OpenAI, *MCP servers* (remote servers and Secure MCP Tunnel):
  https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- MCP, *Streamable HTTP* (2026-07-28 transport change):
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/draft/basic/transports/streamable-http.mdx
- GitHub Docs, *Troubleshooting required status checks* (checks on latest SHA):
  https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks

## Evidence boundary

Source edits and branch commits are not a host execution, package validation
or real ChatGPT app/tool exposure. Runtime status is an observation; a valid
accepted and finalized per-turn envelope is a separate authority.
