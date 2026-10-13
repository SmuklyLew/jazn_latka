# Jaźń 16.3.25.5.115.21.13 — code-first MCP/host/documentation convergence

**Date:** 2026-10-13  
**Status:** implementation candidate, not production acceptance  
**Release identity source:** `latka_jazn/version.py`

## Scope and ground truth

This change addresses the identified split between executable Python runtime
and host-facing prompts/manifests. It **does not** claim to repair ChatGPT host
process creation, to create a deployed remote MCP app, to restore private
MEMORY or to prove an accepted visible Jaźń turn. Those require independent
live-host/deployment evidence.

### Code ownership

- `run.py` is a thin entrypoint; `main.py` owns canonical dispatch.
- Persistent daemon retains session, memory, idempotency and finalization state.
- `latka_jazn/mcp/http_gateway.py` is an authenticated transport adapter.
- `latka_jazn/mcp/finalization_input.py` computes the SHA-256 digest of the
  exact final UTF-8 bytes. Client digest is optional; if present, a mismatch
  fails closed **before any backend finalization call**.
- Continuation token, turn authority, semantic guards and persistence still
  belong to the canonical finalizer, not to the checksum helper.
- `latka_jazn/mcp/host_guidance.py` is the single instruction string for
  registered/Desktop and public HTTP MCP surfaces. It is a hint, not runtime.
- `CHATGPT_BOOTSTRAP.py` remains standalone stdlib cold-boot fallback. A ZIP
  cannot grant a local executor or publish/authorize a remote connector.

### Documentation fixes

`docs/README.md`, `docs/plans/README.md`, `docs/plans/CURRENT_STEP.md`,
`docs/project/CURRENT_STATE.md`, `docs/project/RELEASE_TIMELINE.md`,
`docs/plans/PLAN_EXECUTION_HISTORY.md` and
`docs/runtime/TURN_FINALIZATION_CONTRACTS.md` now distinguish a dynamic
version owner from dated historical snapshots. Additional runbooks describe
code-first ownership and the live-host truth gate. History is preserved.

`tools/docs_truth_audit.py` checks the active markers, the runtime version
against `deploy/chatgpt_mcp/deployment.contract.json`, and the canonical
four model-visible tool names against the startup evidence contract.
`release-hardening.yml` runs this audit prior to compileall/pytest. This
prevents obvious stale-contract releases without turning Markdown into runtime
authority. Model-only substring tests remain supplementary; behavior tests are
still required.

## Security and compatibility boundaries

- No private MEMORY, SQLite/WAL/SHM, tokens or credentials are added to release.
- Existing HTTP callers may continue to send `final_visible_text_sha256`; the
  value must match the adapter-computed SHA-256. New callers may omit it.
- The stdio/private legacy finalization contract remains unchanged.
- Do not reduce server-side continuation, semantic or accepted-turn gates.
- Do not replay a submitted user message; resume the same durable request id.
- MCP Tasks are an extension; the official Python SDK v2.2.0 does not yet
  implement it natively. The Jaźń bridge remains a separately tested adapter.
- The host language model may still be required for `generate_then_finalize`.
  That host generation does not confer lifecycle, persistence or truth authority.

## Verification performed at authoring time

- Fresh SYSTEM ZIP package SHA-256 matched the supplied sidecar, ZIP CRC passed,
  and the standalone bootstrap returned `materialized_operator_ready`.
- Python compile of changed MCP modules, version, audit, tests and entrypoints
  passed for the nine named files.
- Targeted deterministic tests: 36 passed for code-first, loader, deployment,
  hybrid routing and desktop app binding.
- Documentation/contract drift audit: `ok=true`.
- Host runtime `start`: not conversation-ready in this session because its
  loopback health endpoint refused connections; no accepted visible turn claim.
- Full deterministic suite, Pyright, Windows E2E, authenticated real ChatGPT
  MCP ingress and private MEMORY acceptance are **NOT VERIFIED** by this report.
  Release is not production-ready until the corresponding final-SHA CI and
  live-host acceptance gates succeed.

## Required release acceptance

1. On final SHA, run canonical metadata synchronization, compileall,
   `pytest -m "not live_model and not live_mcp"`, Pyright, package smoke and
   release-hardening (Ubuntu and Windows).
2. Test public/registered MCP discovery, all four canonical tools, OAuth
   scopes, 401/403, health vs readiness and protocol negotiation.
3. Test finalization with omitted/correct/mismatched hash, non-ASCII UTF-8,
   oversized text and duplicate/retried requests; assert no second finalization.
4. Deploy to nonproduction, confirm `/healthz` and `/readyz` independently.
5. Connect/refresh the actual ChatGPT app and verify model-callability in the
   **current message**; invoke a fresh `jazn_status` with matching instance,
   version and heartbeat. An installed app or ZIP is not sufficient.
6. Submit two separate user messages exactly once, recover ambiguous transport
   using the same request and require final `action=display_exact` receipts.
7. Test daemon/supervisor restart, rollback and cross-session continuity.
8. Verify MEMORY separately; do not claim autobiographical recall until its
   independent native source/provenance acceptance succeeds.

## References

- OpenAI Agent Plugins packaging and registered app bindings:
  https://developers.openai.com/plugins/build/plugins
- OpenAI MCP tool visibility change:
  https://developers.openai.com/plugins/changelog
- MCP SEP-2663 Tasks extension:
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2663-tasks-extension.md
- MCP Python SDK v2 migration notes and limitations:
  https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md
