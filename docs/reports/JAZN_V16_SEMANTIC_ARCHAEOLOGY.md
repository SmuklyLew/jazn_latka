# Jaźń v16 semantic archaeology map

Date: 2026-08-23

Target branch: `upgrade/v16-full-system-convergence`

This report records semantic forward-ports. It is not a merge plan for the old
branches and does not make either old architecture canonical again.

## `upgrade/jazn-model-bridge-v2` -> v16.0.7

| Historical invariant | Current v16 location | Disposition |
| --- | --- | --- |
| bounded, allowlisted model-visible context | `core/host_response_candidate_guard.py` and `model_guided_response_synthesizer.py` | forward-ported; credential-, raw-row- and SQLite-shaped keys are removed |
| cryptographic context binding | `host_generation_context.context_sha256`, included in runtime and host request hashes | forward-ported |
| explicit allowed memory IDs | `allowed_memory_item_ids` in the persisted phase-1 contract | forward-ported |
| model declares used memory IDs | host reply schema and finalizer candidate guard | forward-ported |
| undeclared or unauthorized memory use is rejected | grounding evaluator plus host candidate guard | forward-ported |
| candidate evaluation before persistence | `persist_chatgpt_host_visible_reply` | forward-ported before final-visible persistence |
| reject known runtime templates | `TemplateRegistry.classify_body` in the host candidate guard | forward-ported |
| RuntimeAnswerValidator before acceptance | host candidate guard | forward-ported; strict for native retained context, compatibility telemetry for reconstructed old phase-1 context |
| old `host_model_bridge.py` as a parallel architecture | none | deliberately not restored |

## `fix/epistemic-rest-consolidation-hardening` -> v16.1.0

The old branch is retained as an evidence source for the collector, claim guard,
hash-chained decision ledger, memory-promotion gate and offline rest pipeline.
Each invariant is re-evaluated against current v16 final-visible, memory and rest
contracts before implementation. Whole commits are not cherry-picked.

## Mandatory exclusions

- `fix/sqlite-runtime-io-hardening`: history-only divergence after merged PR #136;
- `upgrade/local-first-memory-cloud-v155-full`: only semantic review of residual
  changes after PRs #140, #141 and #142; no automatic merge.
