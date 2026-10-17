# Jaźń 16.3.25.5.116.0.34.7 — ChatGPT MCP catalog and MEMORY source convergence

## Status and provenance

**Implementation candidate, NOT deployed as a ChatGPT connector and NOT an accepted private MEMORY package.**

Baseline: master 82705469e8a3acacc9a8797823043a9264b97534; verified SYSTEM portable v16.3.25.5.116.0.34.6 with SHA-256 cc05d87fc5424ac421f30f250d3b3b4563ebbc23da07e7130d34710e9e44db9e.

Branch: upgrade/v16.3.25.5.116.0.34.7-chatgpt-mcp-recovery-convergence. Neither master nor any private-memory database is modified.

## Two confirmed defects

**MCP catalog SSE rejection.** The built-in tools/list probe advertised `Accept: application/json, text/event-stream`, then always rejected a valid Streamable HTTP text/event-stream response. The fix reads only the matching JSON-RPC result, handles keepalive and notification events, supports paginated catalogs, limits bytes/events/pages, refuses malformed or unrelated frames and never sends a user turn. It does not infer current-message ChatGPT tool exposure, daemon readiness or accepted finalization.

**MEMORY source resolver divergence.** The old `memory_root_has_payload()` considered any nonempty raw/layered/sqlite subdirectory, including operational runtime_write files, a MEMORY root candidate. `availability.py` required specific provenance/recall files. A temporary canonical placeholder could therefore hide valid legacy user MEMORY and mislead diagnostics. Both now share one shallow read-only predicate, accepting only nonempty explicit manifest or legacy recall source markers. Explicit root overrides remain authoritative; candidate does not mean native unified readiness. No SQLite or private data is migrated.

## Verification

Focused, locally executed: tests/test_chatgpt_bridge_tool_catalog_probe.py, tests/test_v1160347_chatgpt_mcp_catalog_sse.py, tests/test_optional_memory_attach_convergence.py, tests/test_v1160347_memory_candidate_root_parity.py — **39 passed** on the extracted portable SYSTEM. Syntax compile for the changed Python files passed.

The broader deterministic suite did not complete within the single host execution limit; early failures require investigating on final branch / CI and may involve release-version fixtures or missing optional dependencies. **Do not report a full-suite PASS.** Required gates: full deterministic pytest, compileall, Pyright 0 errors, doctor, package-smoke, Windows/Linux CI, canonical manifest/provenance sync, plugin/MCP live acceptance, final SHA and release package.

## Remaining external blockers

The owned ChatGPT plugin jazn-runtime 0.2.1 points to local `http://127.0.0.1:8080/mcp`. Deployed Cloudflare Worker remains intentionally closed with 503 until secure OAuth/upstream readiness. Installing SYSTEM into ChatGPT sandbox does not register callable tools or keep a Python daemon alive. No account/plugin/deployment changes are performed by this patch. Two consecutive actual ChatGPT `generate/resume/finalize` accepted `display_exact` turns, fresh status, authenticated remote MCP, native MEMORY and restart continuity must be verified separately.

## Evidence and primary sources

- MCP 2026-07-28 spec: https://modelcontextprotocol.io/specification/2026-07-28
- MCP stateless core and transport: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- OpenAI server build/security: https://developers.openai.com/plugins/build/mcp-server
- OpenAI plugin connect/refresh: https://developers.openai.com/plugins/deploy/connect-chatgpt
- SQLite Online Backup API (for future MEMORY promotion, not exercised here): https://www.sqlite.org/backup.html
- Existing repository issues: https://github.com/SmuklyLew/jazn_latka/issues/340 and https://github.com/SmuklyLew/jazn_latka/issues/59
