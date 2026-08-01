# Focused review guide

Reviewers should inspect these invariants first:

1. No path from `jazn_generate_visible_reply` returns host-generated text as visible output before finalization.
2. `jazn_finalize_reply` cannot receive or override runtime-owned identity, timestamp, turn, trace, or contract fields.
3. The continuation token is bound to one pending request, is not stored in plaintext, expires, and cannot be replayed.
4. The canonical pending claim/consume and persistence path remains the only way to create a host-visible final reply.
5. Gateway authentication is distinct from external MCP client authentication.
6. Runtime phase-one success does not commit a final answer or session-visible text.
7. Status truth differentiates live endpoint evidence from offline snapshots.
8. Existing CLI JSONL compatibility still uses the same finalization store and gate.

Security-sensitive files:

- `latka_jazn/core/chatgpt_host_pending_store.py`
- `latka_jazn/bridge/secure_host_runtime_gateway.py`
- `latka_jazn/mcp/tools/jazn_finalize_reply.py`
- `latka_jazn/mcp/server.py`
- `latka_jazn/core/runtime_session.py`
