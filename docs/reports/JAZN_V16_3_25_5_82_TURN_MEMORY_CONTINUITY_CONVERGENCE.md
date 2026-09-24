# Jaźń v16.3.25.5.82 — turn/memory continuity convergence

## Problem reproduced

The live 79.3 runtime remained healthy at the process level, but a prior durable phase-1 request stayed in `awaiting_host_finalization`. Every later message waited behind that predecessor for the bounded 8-second finalization gate, then failed with `host_finalization_timed_out`, while the predecessor stayed pending. The empty `turn_id` / `trace_id` seen on those successor diagnostics was therefore a downstream symptom: those successor turns never executed.

A separate defect was found in `LegacyMemoryRecovery`: it hard-coded `<active_root>/memory`, although the rest of the runtime resolves persistent MEMORY through the canonical host-level root / `JAZN_MEMORY_ROOT`. This produced false `conversation_archive_manifest_missing` and `journal_and_layered_sources_missing` reports after a valid external MEMORY attach.

## Repair

- preserve the serialized Issue #185 finalization gate;
- after the bounded gate expires, atomically expire only a predecessor whose durable host request is still **pending/unclaimed**;
- never abandon `claimed` or `indeterminate` phase-2 work;
- execute the already-submitted successor exactly once in the same daemon after safe supersession;
- preserve request identity and replay protection in the durable host-request store;
- make durable directory placement authoritative across the pending -> expired atomic move;
- route `LegacyMemoryRecovery` through `JaznConfig.memory_root`;
- document one maintenance window: stop once, attach/repack, recover/normalize/wake while still stopped, start once, then verify/resume/finalize.

## Ahead/base convergence

This fix is based on `upgrade/v16.3.25.5.81-persistent-remote-mcp-runtime` rather than 79.3 master, preserving its 34 commits ahead / 0 behind state. The open Memory Studio PR #281 does not modify the active daemon, durable host-request store, or active memory-recovery implementation touched here; it can remain an independent integration line.

## External design evidence

- OpenAI Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- MCP Tasks extension 2026-07-28: https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks
- Amazon Builders' Library, idempotent APIs: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- Microsoft transient-fault guidance: https://learn.microsoft.com/en-us/azure/well-architected/design-guides/handle-transient-faults

The resulting policy keeps the persistent daemon as the runtime owner, uses bounded waits, avoids blind replay, preserves caller request identity, and prevents a stale unclaimed finalization record from blocking all future conversation turns indefinitely.

## Validation before push

On the verified 79.3 code bytes shared by the affected files (the v81 branch does not modify them):

- focused regression: 25 passed;
- lifecycle/MCP/security/memory selection: 110 passed;
- AGENTS/agent-boundary selection: 18 passed;
- compileall: PASS;
- broad active-suite smoke reached 388 passed / 6 skipped before stopping on a repository-history test that requires a real `.git` directory; the SYSTEM ZIP working copy intentionally has no `.git`.

Final branch-wide validation remains GitHub Actions' responsibility because v81 itself is an ahead branch and was not locally cloned into this sandbox.
