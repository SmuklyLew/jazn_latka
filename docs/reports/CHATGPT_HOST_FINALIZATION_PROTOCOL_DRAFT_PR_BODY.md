# Fix ChatGPT host finalization protocol

## Summary

- replace prompt-only coordination with authenticated two-phase MCP flow;
- add opaque expiring one-shot continuation tokens;
- bind immutable identity/timestamp/turn fields server-side;
- route finalization through canonical pending persistence;
- fix daemon auth, runtime intermediate state, status readiness, and host runbook;
- add regression tests and operational documentation.

## Validation

Draft until GitHub Actions compilation, pytest, doctor, package smoke, diff checks, and canonical metadata synchronization complete.
