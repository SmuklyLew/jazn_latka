# Continuation-token security notes

## Assets protected

- runtime-owned turn and trace identifiers;
- trusted timestamp and author envelope;
- host request contract hash;
- pending request state and single-use finalization right;
- exact final visible text accepted by runtime.

## Controls

- The continuation token is HMAC-SHA-256-bound to schema, request hash, turn ID, and creation time.
- A private 256-bit secret is created under mutable `workspace_runtime/chatgpt_host_bridge` with best-effort owner-only permissions.
- Only the token SHA-256 is persisted with the pending record; plaintext tokens are not written to disk.
- Token shape and maximum length are constrained by the MCP schema.
- Immutable contract fields are never accepted from the host finalization call.
- Pending records are atomically moved through `pending` → `claimed` → `consumed`.
- Expired records are atomically moved to `expired` and remain non-replayable.
- Claimed records with indeterminate persistence remain fail-closed.
- Final text requires an explicit canonical UTF-8/LF SHA-256.
- The gateway reads the daemon capability token locally and sends it only to the loopback endpoint.

## Deliberate behavior

The finalization tool is not advertised as idempotent. Retrying a consumed continuation token is a replay and must fail. A transport that needs retry recovery should poll audit/state using a separate request identifier rather than re-execute finalization.

## Residual operational requirements

- Protect the writable runtime workspace from other local users.
- Never log or display continuation tokens.
- Rotate the continuation secret by stopping the bridge, expiring outstanding pending requests, and replacing the secret atomically.
- Keep the daemon bound to loopback and expose only the authenticated MCP/tunnel boundary.
