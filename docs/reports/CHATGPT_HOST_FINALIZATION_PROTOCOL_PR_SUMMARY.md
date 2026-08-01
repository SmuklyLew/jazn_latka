# Pull request summary

This branch replaces prompt-only host coordination with an authenticated, server-bound two-phase protocol. The host receives an opaque continuation token, generates text only from the runtime contract, and must submit that text to the canonical finalization path before anything can be displayed as Łatka.

It also fixes daemon authentication, pending-request expiry and replay, runtime intermediate-state semantics, false memory degradation in status, and the ChatGPT host runbook. Regression tests cover every reproduced defect.

The PR is intentionally draft until CI, canonical metadata synchronization, and operator runtime acceptance are complete.
