# Jaźń v16.3.25.5.116.0.1 — host-tool ingress + MCP Tasks ownership (checkpoint)

Status: **implementation checkpoint, NOT release-ready**.
Parent line: `master` v16.3.25.5.115.21.14.
Scope: isolated changes on `update/v16.3.25.5.116-runtime-ingress-security-convergence`.

## Implemented

- Explicit Polish research imperatives now request and require real host `web.run` evidence, rather than falling through to ordinary dialogue. Tool *requests* never imply tool *availability*.
- Durable MCP task registry records `owner_subject`, `owner_transport`, `authorization_revision` with additive SQLite migration. Existing unowned records are never assigned to a remote caller implicitly.
- HTTP Tasks bridge carries the verified OAuth principal; task creation/read/cancel/input and public `jazn://task/` resource reads are scoped to the caller. Unknown/cross-subject tasks fail closed, without exposing record existence.
- Release identity and selected startup/deployment contract markers advanced to `16.3.25.5.116.0.1`.
- New regression suites cover research intents, no-host-tool behavior, cross-principal denial, persistence and v115 database schema migration.
- Original modified test bytes preserved under `tests/archive/v16.3.25.5.115.21.14-*` before test changes.

## Verification and constraints

- 22 targeted research and policy tests passed.
- 19 targeted registry/protocol tests passed.
- An intermediate deterministic-suite run passed 2148 tests, skipped 21, then stopped because the locally rebuilt Git directory lacked an `origin` remote; the corresponding targeted stability suite passed 26/26 after configuring `origin`.
- The local test environment lacks the optional `mcp` SDK, so HTTP SDK integration tests and official conformance are **not verified**.
- Synthetic local git checkout from verified SYSTEM ZIP is **not** byte-identical to a fresh GitHub clone: canonical release metadata, release-build checks and final CI must run from the actual GitHub branch SHA.
- No public OAuth endpoint or real ChatGPT MCP binding was deployed/verified. Active ChatGPT remote tools remain unavailable on the current message.
- No private MEMORY data was attached, modified or committed.
- The Tasks `inputResponses` runtime gateway remains fail-closed: transport is not implemented and no successful ACK should be claimed.


## Additional principal-provenance hardening

The production Tasks bridge now passes verified identity using a Python
`ContextVar` scoped to one call, rather than reading client-controlled JSON
`params._meta`. A forged metadata marker cannot authorize a task. The
trusted local JSON request path refuses access to tasks with a public owner.
Public HTTP and Tasks OAuth authenticators require an explicit nonempty
user `subject`: `client_id` and the constant `oauth-client` are no longer
used as substitutes for user identity.

A new regression test verifies that spoofed metadata does not authorize
a caller. Test Studio uses stable purpose-based filenames and a canonical
synchronized catalog of 2267 definitions.

## Mandatory remaining gates

1. Complete official MCP 2026-07-28 conformance against a live isolated server in CI with reviewed pinned dependencies. Tasks extension tests are separate hard blockers when advertised.
2. Implement task input bridge with runtime ACK, idempotent input keys and preserved request lineage.
3. Finish daemon dependency inversion and remove late monkey-patches as required by v116 plan, without changing single canonical runtime/finalization ownership.
4. Run Pyright zero errors/warnings, deterministic full pytest, packaging, metadata synchronization, Linux and Windows persistent-runtime E2E, optional dependency/feature CI.
5. Audit authenticated principal provenance at every public and local MCP ingress boundary; never trust client-supplied `_meta` alone.
6. Verify live connector availability in a new ChatGPT conversation and two sequential finalized turns.
7. Do not merge until all blockers are explicitly resolved on final SHA.

## Primary references

- Project plan: `docs/plans/JAZN_V16_3_25_5_116_PROTOCOL_CONFORMANCE_DEPENDENCY_INVERSION_CONVERGENCE_PLAN.md`.
- MCP: https://modelcontextprotocol.io/specification/2026-07-28
- Conformance: https://github.com/modelcontextprotocol/conformance
- OpenAI auth: https://developers.openai.com/plugins/build/auth
