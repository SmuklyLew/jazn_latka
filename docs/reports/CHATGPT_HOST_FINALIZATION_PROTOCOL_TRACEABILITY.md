# Defect-to-fix traceability

| Defect | Implementation |
|---|---|
| Host could display text before runtime acceptance | action-aware generation tool; only finalizer returns `display_exact` |
| Gateway received daemon 401 | daemon capability token added to every loopback request |
| Valid phase one was treated as tool error | `generate_then_finalize` is a successful non-visible action |
| Finalizer trusted host immutable fields | opaque token resolves server-side binding; strict schema removes those fields |
| Finalizer bypassed pending store | finalizer calls canonical `persist_chatgpt_host_visible_reply` |
| No expiry/cleanup | TTL, expired quarantine, cleanup and store status |
| Replay could be returned as idempotent success | finalizer removed from generic idempotent replay path; consumed token fails closed |
| Phase one counted as daemon failure | runtime session marks complete phase one `awaiting_host_finalization` with execution success but no final-answer commit |
| Memory status false degradation | readiness resolver reads top-level, ping, or nested access status explicitly |
| Snapshot confused with live truth | runbook and status payload mark snapshot offline and ineligible for activation proof |
