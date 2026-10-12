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

| Historical invariant | Current v16 location | Disposition |
| --- | --- | --- |
| observable evidence classes stay distinct | `core/epistemic_evidence.py` | forward-ported with identifier-backed counts and verified rest report binding |
| strong self/runtime claims fail closed | `core/epistemic_claim_guard.py` | forward-ported and applied to direct and host-finalized visible replies |
| confidence never turns inference into fact | structured claim guard | forward-ported with explicit inferred/hypothetical/synthetic states |
| bounded decision audit without chain-of-thought | `core/epistemic_decision_ledger.py` | forward-ported to canonical runtime workspace with hash-chain validation |
| automatic L3 forbidden | `memory/memory_promotion_gate.py` and `rest_consolidation.py` | forward-ported; real anchors now require both a source locator and a valid integrity hash |
| conflict requires review | memory promotion gate | forward-ported by stable source identity and divergent content hashes |
| useful rest is independent of Dream | `memory/offline_rest_consolidation.py` and `core/rest_cycle_controller.py` | forward-ported as replay -> offline consolidation -> optional dream -> evaluation -> gate |
| old ledger path under version root | none | corrected; decision ledger lives only in the canonical external runtime workspace |

No commit from the old branch was cherry-picked. The historical code was used
only to recover semantics and was adapted to current v16 finalization, turn
staging, memory-tier and single-workspace contracts.

## Mandatory exclusions

- `fix/sqlite-runtime-io-hardening`: history-only divergence after merged PR #136;
- `upgrade/local-first-memory-cloud-v155-full`: only semantic review of residual
  changes after PRs #140, #141 and #142; no automatic merge.
