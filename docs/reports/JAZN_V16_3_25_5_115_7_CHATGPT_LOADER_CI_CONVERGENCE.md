# Jaźń v16.3.25.5.115.7 — ChatGPT loader / MCP CI convergence

## Base and observed failure

Source branch: `fix/v16.3.25.5.115.6-chatgpt-mcp-exposure-recovery`, from
commit `ff0487df47e2171926bb61c2a47e872cf8777fe0`. The full Ubuntu verification in
[release-hardening run 37782283284](https://github.com/SmuklyLew/jazn_latka/actions/runs/37782283284)
reported 9 failing / 2157 passing / 2 skipped tests. These failures concerned the
ChatGPT Project loader's exact operational statements, not an authenticated
ChatGPT remote MCP acceptance.

## Changes

- Preserve the complete fresh-message toolset gate, least-privilege policy,
  one process probe, same-request resume and accepted display_exact finalization.
- Restore explicit, tested host-executor failure generation/unknown state,
  ChatGPT Library search, SHA-256 materialization, separate MEMORY discovery and
  current-turn tool evidence semantics. Remain under the 5000-character limit.
- Advance the distribution, startup and public deployment contract to 115.7.
- Preserve the active 115.6 test byte-for-byte under tests/archive before
  updating the active test's version gate.
- Add a regression test for synchronized contract identities and host truth gates.

## Limits and external acceptance

Green CI is not proof of current-message tool availability inside ChatGPT.
A registered `jazn-runtime` plugin pointing to localhost is not cloud ingress.
Production remote MCP requires a reachable HTTPS endpoint with verified
authentication (or supported Secure MCP Tunnel), user account registration and
a *fresh* four-tool visibility + real jazn_status + finalization test.
Never advertise the private daemon directly without authentication.
The ChatGPT project loader cannot enable plugins or force host tool exposure.

## Verification and rollback

Run targeted loader tests, non-live pytest, compileall, Pyright,
persistent-runtime-e2e on Windows/Linux and release-hardening.
For rollback use the immutable source branch HEAD above, rather than
overwriting release manifests by hand. No MEMORY, secrets or runtime state
belong in this change.
