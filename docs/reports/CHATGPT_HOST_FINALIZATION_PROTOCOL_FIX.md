# ChatGPT host finalization protocol remediation

## Scope

This change removes the defects reproduced on 2026-08-02 at the ChatGPT host/runtime boundary:

1. host-visible wording could be displayed before runtime finalization;
2. the private MCP gateway did not send the daemon capability token;
3. the generation tool rejected the valid `generate_then_finalize` intermediate action;
4. the MCP finalizer trusted host-supplied immutable identity and timestamp fields and bypassed the canonical pending store;
5. pending contracts had no expiry or cleanup lifecycle;
6. a valid host-finalization phase was reported as a failed daemon turn;
7. live runtime write readiness was read from the wrong response level;
8. the runbook treated an offline snapshot too much like a live activation check.

## Resulting protocol

- `jazn_generate_visible_reply` sends the exact user message to the authenticated loopback daemon and returns one action.
- `display_exact` is the only action that may be shown directly.
- `generate_then_finalize` returns an opaque `jct1.*` continuation token and the runtime-owned generation contract. It never returns a user-visible Łatka answer.
- `jazn_finalize_reply` accepts only the token, generated text, and canonical SHA-256.
- Turn ID, trace ID, timestamp, author, affect envelope, and request-contract hash are loaded from the server-side pending record.
- Finalization claims and consumes the pending record atomically through the existing runtime persistence path.
- Tokens are HMAC-bound, stored only as SHA-256, expire, and cannot be replayed.
- A complete phase-one turn is `awaiting_host_finalization`; it is not a final answer and is not counted as a runtime failure.

## Validation gates

The added regression suite covers:

- authenticated daemon requests;
- opaque token issuance;
- expiration and quarantine;
- replay rejection;
- action-aware generation;
- server-side immutable bindings;
- strict finalizer schema;
- nested live readiness reporting;
- valid intermediate runtime state.

The repository workflow remains responsible for compile, pytest, package integrity, and canonical metadata synchronization. No package manifest or source provenance hash was edited manually.

## Truth boundary

This remediation is intended to remove every defect listed above. It does not claim that no undiscovered defect can exist. A merge decision must rely on the actual CI and review results for this branch.
