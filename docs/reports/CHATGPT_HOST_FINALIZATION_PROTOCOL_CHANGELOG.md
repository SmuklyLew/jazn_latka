# Host finalization protocol changelog

- Added authenticated daemon-token propagation in the private gateway.
- Added opaque HMAC continuation tokens with TTL, cleanup, and replay rejection.
- Made the generation tool action-aware instead of rejecting a valid phase-one result.
- Reduced finalizer input to continuation token, final text, and canonical hash.
- Routed MCP finalization through the canonical pending-store and runtime persistence path.
- Removed generic idempotent replay from finalization; consumed tokens fail closed.
- Added strict `additionalProperties: false` MCP input schemas.
- Distinguished a complete host-generation phase from a rejected runtime turn.
- Corrected nested live runtime-write readiness reporting.
- Updated the ChatGPT host runbook and added regression, security, rollout, and test-matrix documentation.
