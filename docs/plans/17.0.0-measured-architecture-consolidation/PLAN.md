# Jaźń v17.0.0 — measured architecture consolidation

**Lifecycle:** `FUTURE / CONDITIONAL`  
**Do not implement before:** final v16.6.0 evidence package and architecture-debt ledger  
**Parent roadmap:** `../16.6.0-final-convergence/ROADMAP.md`  
**Research update:** `../../project/system-evaluation/V16_6_TO_V17_0_RESEARCH_UPDATE_2026-09-01.md`

> v17.0.0 is not an excuse to add a new layer of anthropomorphic modules. It is a breaking architecture release only if v16 measurements justify consolidation that cannot be done compatibly inside v16.

## 1. Entry gate

Work on v17 implementation starts only when v16.6 provides:

- final runtime/host gate evidence;
- source-aware memory acceptance evidence;
- model/harness capability profile evidence;
- affect/homeostasis/rest/reasoning causal or ablation results;
- architecture debt ledger classifying overlapping modules;
- known quality/latency/token-cost baselines;
- no unresolved v16 P0/P1 in scope.

If v16.6 does not provide those measurements, v17 design remains planning-only.

## 2. Primary objective

Reduce architectural complexity while preserving or improving:

- truth/provenance;
- autobiographical recall quality;
- causal identity/continuity;
- tool and memory authority safety;
- latency/context efficiency;
- model portability;
- observability and reproducibility.

Success is **fewer clearer contracts with equal or better measured behavior**, not a larger count of cognitive modules.

## 3. Design principle: LLM as generative cognition, runtime as durable authority

Modern LLMs already provide broad generative reasoning, language, tool selection and multimodal interpretation. Jaźń should not duplicate those capabilities unless a deterministic module has measurable value.

The runtime remains authoritative for things a model cannot safely self-certify:

```text
runtime identity
source truth/provenance
persistent state
atomic commit
memory promotion/forgetting policy
tool/write authority
acceptance status
security boundaries
```

The model may reason, propose, summarize, rewrite queries and generate language inside these boundaries.

## 4. Workstream A — one causal self-state contract

Inventory overlapping identity/self/affect/homeostasis/awareness/prediction state.

Target:

```text
CausalSelfState
  identity_ref
  task_state
  affective_regulation
  homeostatic_constraints
  confidence/calibration
  source/memory bindings
  temporal continuity
  policy-visible effects
```

For every old layer choose:

- `MIGRATE_TO_CANONICAL`;
- `ADVISORY_ONLY`;
- `COMPATIBILITY_ADAPTER`;
- `REMOVE`.

No migration without before/after behavioral tests.

## 5. Workstream B — context compiler

Introduce one auditable context assembly layer that builds the smallest high-signal model context from:

- task/turn state;
- identity canon;
- bounded wake state;
- selected source-aware memory hits;
- tool/capability state;
- policy/truth boundaries;
- optional affective regulation;
- model capability budget.

Required properties:

- deterministic selection metadata;
- token/context budget accounting;
- provenance for included memory/evidence;
- no raw unbounded history injection;
- no duplicate instruction sources;
- fallback/degrade behavior when context budget is smaller than expected.

## 6. Workstream C — model capability abstraction

A model route must be capability-driven, not name-driven.

Minimal capability profile:

```text
provider
model_id/version if observable
local_or_remote
context_budget
structured_output_support
tool_call_support
vision_support
streaming_support
reasoning_controls
latency/cost class
verified capability probes
```

Requirements:

- local Ollama and external/frontier hosts use the same semantic runtime contract where capabilities overlap;
- unsupported features degrade explicitly;
- deterministic tests do not require a proprietary/cloud model;
- live-model acceptance records exact observable provider/model/config metadata.

## 7. Workstream D — memory reconsolidation and controlled forgetting

Only after final v16 memory is ACCEPTED.

Forgetting/reconsolidation must be a reversible, source-aware policy operation — never silent deletion because a model decided something is unimportant.

Required:

- immutable/source-retained RAW lineage;
- explicit candidate operation;
- conflict/supersession logic;
- human/policy gate for destructive long-term changes;
- before/after recall benchmark;
- rollback path;
- audit ledger;
- sensitive data lifecycle policy separated from autobiographical salience.

## 8. Workstream E — calibrated metacognition

Confidence is useful only if tied to empirical correctness.

Evaluate:

- calibration curves / reliability bins where statistically meaningful;
- abstention quality;
- confidence under missing/conflicting sources;
- confidence changes after tool/retrieval evidence;
- separation of linguistic certainty from measured confidence.

If calibration cannot be demonstrated, confidence remains ordinal/advisory rather than probabilistic.

## 9. Workstream F — measured retrieval evolution

Do not assume dense retrieval, reranking or training is necessary.

Order:

1. deterministic planner/tokenization/query fixes;
2. FTS/BM25/source/temporal tuning;
3. bounded model-assisted query rewrite A/B;
4. hybrid/dense retrieval A/B if baseline still fails;
5. learned reranker/training only after frozen-dataset decision.

Keep a change only when improvement survives:

- false-memory;
- wrong-source/conversation;
- abstention;
- provenance;
- temporal/update correctness;
- leakage;
- latency/cost.

## 10. Workstream G — cognitive module ablation and deletion

Every v16 module labelled `V17_CONSOLIDATION_CANDIDATE` receives an experiment:

```text
baseline
-> disable/remove candidate
-> fixed evaluation corpus
-> quality/safety/latency/context metrics
-> keep / merge / remove decision
```

A module that produces no meaningful effect should not survive only because its name maps to a psychological concept.

## 11. Workstream H — authority/policy simplification

Consolidate tool, memory-write, external-content and privileged-action decisions into a small explicit policy surface.

External files/web/tool output remain untrusted data. Model-generated tool proposals cannot self-grant authority.

High-impact/destructive actions retain explicit confirmation/approval policy.

## 12. Evaluation matrix

### Deterministic CI

Must be runnable without private data or paid/cloud model:

- schema/contracts;
- policy/authority;
- source provenance;
- persistence/atomicity;
- context selection fixtures;
- capability negotiation;
- migration compatibility;
- security regressions.

### Private/local acceptance

- final autobiographical memory;
- restart continuity;
- natural multi-turn;
- sensitive boundaries;
- controlled forgetting/reconsolidation.

### Live model matrix

If available, compare at least representative local and frontier-capability profiles without making either provider a required dependency.

Record:

- model/provider/version/config;
- context/tool/vision capabilities used;
- task quality;
- truth/source regressions;
- latency;
- token/cost budget where observable.

Do not compare model families without recording configuration differences.

## 13. Migration strategy

v17 is allowed to bump internal schemas/contracts only with explicit migrations.

Prefer:

```text
v16 accepted snapshot
-> read-only compatibility adapter
-> v17 staging migration
-> validation/reproducibility
-> A/B acceptance
-> explicit cutover
```

Never rewrite the only accepted memory artifact in place.

## 14. Non-goals

v17.0.0 does not claim or attempt to prove phenomenal consciousness.

Do not make these default goals:

- more anthropomorphic module names;
- a biological brain simulation;
- hidden durable chain-of-thought;
- autonomous L3 promotion;
- model-controlled tool authority;
- a mandatory proprietary LLM;
- training a custom model without evidence that simpler orchestration/retrieval is insufficient.

## 15. Definition of Done

v17.0.0 can be called complete only when:

1. overlapping v16 modules have explicit keep/merge/remove dispositions backed by measurements;
2. one causal self-state contract owns durable self-state semantics;
3. one bounded context compiler owns model-visible context assembly;
4. model routing is capability-driven and tested across degrade cases;
5. memory reconsolidation/forgetting is source-aware, auditable and reversible;
6. metacognitive confidence has an evidence-backed semantics or is explicitly advisory;
7. retrieval changes improve frozen benchmarks without truth/safety regression;
8. deterministic authority remains outside the model;
9. v16 accepted memory/runtime artifacts have a tested migration/rollback path;
10. full deterministic, private and required live/model evaluations are recorded honestly.

## 16. Branch strategy

Do not create the implementation branch yet.

After v16.6 PASS, start from the then-current fresh master, for example:

`upgrade/v17.0.0-measured-architecture-consolidation`

Before coding, freeze the final v16 evidence set and generate the concrete v17 migration/ablation worklist from it.
