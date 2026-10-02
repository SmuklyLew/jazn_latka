# Jaźń v16.3.25.5.96.1 — system coherence convergence

## Scope

This release starts from the post-PR #303 master and converts the remaining
actionable MCP findings into code-level invariants rather than documentation-only
claims. It intentionally does not fabricate external ChatGPT capability or a
successful real-account acceptance run.

## Confirmed findings fixed

1. **Unbounded usable task lifetime.** The task registry advertised a finite
   `ttlMs` but `tasks/get` never used it as a backstop. SEP-2663 permits a
   server to fail a task after `createdAt + ttlMs`. v96 does so before another
   runtime poll.
2. **Wrong `input_required` polling semantics.** A persisted
   `input_required` task was non-terminal, so a repeated `tasks/get` called
   `jazn_resume_visible_reply` again. The extension specifies that
   `tasks/get` should keep surfacing the outstanding `inputRequests` snapshot
   until client input is supplied. v96 returns the persisted snapshot without
   runtime re-entry.
3. **Cross-process write serialization.** The store had an `RLock`, WAL and a
   SQLite busy timeout, but read/modify/write state transitions began as the
   default DEFERRED transaction. v96 reserves the write transaction with
   `BEGIN IMMEDIATE` for create, update and cancel state changes.
4. **Public exception-detail leakage.** An unexpected polling exception was
   copied verbatim into the task JSON-RPC error message. v96 keeps the stable
   exception class while suppressing exception text that could contain operator
   paths, URLs or other sensitive detail.
5. **Cancellation race window.** Cancellation used a separate `get()` followed
   by `update()`. v96 performs terminal-state check and cancel-intent mutation
   in one immediate write transaction.

## Explicit non-change: custom Tasks HTTP bridge

The bridge is retained. As of this release, the official MCP Python SDK v2
supports the 2026-07-28 protocol core but its migration guide and roadmap still
state that SEP-2663 Tasks dispatch is not implemented. Jaźń therefore keeps the
bridge narrow: only task-capable generate plus `tasks/get|update|cancel` are
intercepted; all other requests remain owned by the official SDK.

## Security / OAuth review

The public ingress continues to use the MCP SDK bearer-auth middleware. The
Jaźń RFC 7662 verifier binds tokens to the configured resource audience; the SDK
middleware rejects expired `AccessToken.expires_at` values and mismatched
resource identifiers. RFC 7662 makes `iss` optional in an introspection
response, so this release does not incorrectly require a claim the standard
does not require. When `iss` is present, Jaźń already requires it to match the
configured issuer.

OpenAI's production requirements remain unchanged: stable HTTPS Streamable HTTP,
authorization on private/user-specific actions, protected-resource/OAuth
discovery, per-request token verification, scopes, and a real Developer Mode or
plugin connection for final acceptance.

## Regression coverage

`tests/test_mcp_task_lifecycle_bounds.py` adds deterministic coverage for:

- TTL expiry before runtime polling;
- stable repeated `input_required` snapshots;
- exception-detail redaction;
- idempotent creation from independent store instances;
- idempotent cancellation and terminal-state preservation;
- rejection of negative TTLs.

The persistent-runtime E2E workflow runs this file on both Ubuntu and Windows.

## External truth boundary

A green repository PR proves the code/test/release contracts exercised by CI. It
does **not** prove that a particular ChatGPT account currently has the Jaźń app
installed or that a public deployment is reachable. Real ingress acceptance
still requires a deployed HTTPS `/mcp` endpoint and a host-observed call in a
fresh ChatGPT conversation. That evidence must be collected outside this
repository and must never be synthesized by CI.


## CI follow-up 16.3.25.5.96.1

The first full deterministic release-hardening run exercised 1,934 tests and
found exactly two failures: both were stale release-identity assertions left on
the 16.3.25.5.95.1 line. The functional MCP/SQLite changes were not the failing
surface. Before updating the active tests, their exact source versions were
archived under
`tests/archive/v16.3.25.5.96.1-release-identity-fix/`.

The active release-identity checks now assert the v96.1 system-coherence line
with stable purpose names rather than continuing to describe the prior v95.1
ChatGPT-ingress release.
