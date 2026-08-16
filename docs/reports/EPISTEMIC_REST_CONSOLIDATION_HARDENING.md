# Epistemic and Rest Consolidation Hardening

## Scope

This branch is an architectural hardening update, not a decorative feature patch. It hardens four runtime boundaries:

1. strong autobiographical self-claims must be evidence-backed and fail closed;
2. evidence must be collected from machine-observable runtime artifacts rather than inferred from generated prose;
3. every epistemic decision concerning a strong self-claim must be auditable without storing private model chain-of-thought;
4. idle/rest work must continue deterministically without a dream model, while synthetic dream output remains separated from factual memory.

The implementation deliberately does **not** add a generic LLM `TruthChecker`. Arbitrary semantic fact checking by another unconstrained language-model call would move the hallucination problem rather than solve it.

## Research basis

### Offline replay and consolidation

Tadros et al., *Sleep-like unsupervised replay reduces catastrophic forgetting in artificial neural networks*, Nature Communications 13, 7742 (2022), DOI: 10.1038/s41467-022-34938-7.

The paper demonstrates that an offline replay phase can perform useful consolidation independently of ordinary online task input. Engineering implication: replay/consolidation must remain a real operation even when natural-language dream generation is unavailable.

Primary source: https://www.nature.com/articles/s41467-022-34938-7

### Brain-inspired and generative replay

Van de Ven et al., *Brain-inspired replay for continual learning with artificial neural networks*, Nature Communications 11, 4069 (2020), DOI: 10.1038/s41467-020-17866-2.

Shin et al., *Continual Learning with Deep Generative Replay* (2017), arXiv:1705.08690.

Replay can use stored or generated representations to protect earlier knowledge. Generated replay material is a learning/consolidation mechanism; it is not evidence that a real-world or autobiographical event occurred.

### Stability/plasticity

Kirkpatrick et al., *Overcoming catastrophic forgetting in neural networks*, PNAS 2017 / arXiv:1612.00796.

Continual learning requires explicit constraints protecting earlier knowledge. Jaźń therefore routes memory promotion through a deterministic gate rather than allowing generated rest content to silently become canonical memory.

### Imagination/world-model simulation

Hafner et al., *Mastering Diverse Domains through World Models* (DreamerV3), arXiv:2301.04104.

Imagined trajectories can be useful internal simulation. They remain simulations. Jaźń preserves the existing `DreamScene.factual_claim_allowed == False` boundary and treats dream output as synthetic provenance, never as self-authenticating evidence.

### Retrieval, evidence and provenance

Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, arXiv:2005.11401.

Petroni et al., *KILT: a Benchmark for Knowledge Intensive Language Tasks*, arXiv:2009.02252.

Explicit non-parametric memory and provenance improve grounding and make knowledge updatable, but retrieval alone does not prove every generated statement. Jaźń therefore stores source class and source identifiers separately from visible prose.

### Calibration is not a truth oracle

Kadavath et al., *Language Models (Mostly) Know What They Know*, arXiv:2207.05221.

Huang et al., *Uncertainty in Language Models: Assessment through Rank-Calibration*, arXiv:2404.03163.

Model uncertainty is useful evidence about model behavior, but confidence is not equivalent to correctness. Structured claims originating from `model_inference` remain `inferred` even when confidence is high.

## Runtime architecture

### 1. `EpistemicEvidenceCollector`

`latka_jazn/core/epistemic_evidence.py`

This component performs bounded evidence collection without model inference.

Current inputs:

- latest hash-verified rest wake report;
- explicitly supplied daemon/background event metadata;
- explicitly supplied memory source identifiers;
- explicitly supplied external/tool source identifiers.

Important properties:

- a missing rest database yields zero dream/rest evidence;
- an integrity-failed rest report yields zero positive rest evidence;
- counts cannot manufacture identifiers;
- external and memory evidence are never inferred from response wording.

### 2. `EpistemicClaimGuard`

`latka_jazn/core/epistemic_claim_guard.py`

The guard has two deliberately separate APIs.

#### Raw visible-self-claim enforcement

Regex detection is used only for narrow claims that the runtime can verify deterministically:

- dream activity;
- autonomous background activity.

A positive dream claim requires all of:

- `rest_continuity_status == rest_verified`;
- `rest_cycle_count > 0`;
- at least one persisted dream scene identifier/hash;
- a hash-verified wake report SHA.

A positive background-work claim requires all of:

- verified live daemon evidence supplied by the runtime;
- one or more recorded background events;
- concrete event identifiers.

Daemon presence by itself is insufficient.

#### Structured epistemic claims

Broader claims are represented using explicit source classes:

- current user message;
- user-confirmed memory;
- source-recorded memory;
- canonical memory;
- tool/web source;
- runtime event;
- verified rest report;
- model inference;
- hypothesis;
- synthetic dream;
- fiction;
- unknown.

Structured claim outcomes include:

- `supported`;
- `inferred`;
- `hypothetical`;
- `synthetic`;
- `unsupported`;
- `contradicted`.

A high-confidence model inference remains `inferred`; it cannot become `supported` merely through confidence.

### 3. `EpistemicDecisionLedger`

`latka_jazn/core/epistemic_decision_ledger.py`

Strong visible-self-claim assessments are persisted to an append-only SQLite ledger in `workspace_runtime/epistemic_decisions.sqlite3`.

The ledger stores:

- turn/trace identifiers;
- claim kind/status;
- hash of matched visible text rather than private reasoning;
- required evidence names;
- bounded evidence snapshot;
- reason code;
- previous-entry hash;
- current entry hash.

`validate_chain()` checks both SQLite integrity and the hash chain. This provides an auditable decision trail without persisting private chain-of-thought.

### 4. Final visible reply integration

`latka_jazn/core/final_visible_reply_capture.py`

Epistemic enforcement is integrated at the final visible capture boundary, after generation but before the visible reply is accepted/persisted.

When explicit epistemic evidence is absent, final capture automatically invokes `EpistemicEvidenceCollector` using the active `JaznConfig`. Therefore a real persisted wake report can satisfy dream evidence without the host manually inventing fields.

If a strong claim is detected:

1. evidence is collected;
2. the claim is assessed fail-closed;
3. unsupported/contradicted claims raise `EpistemicClaimViolation`;
4. accepted/negated assessments are written to the epistemic ledger;
5. the ledger hash chain is validated;
6. only then may final capture complete.

### 5. Model-free rest consolidation

`latka_jazn/memory/offline_rest_consolidation.py`

Every eligible rest cycle performs deterministic consolidation before dream generation.

The pass checks:

- replay count;
- real-source anchor count;
- inferred/symbolic count;
- replay content hashes;
- bounded provenance completeness;
- exact duplicate content;
- unique source identities;
- cases where the same source identity points at multiple content hashes;
- truth-status distribution.

A source-identity collision is reported as a review candidate. The deterministic pass deliberately does not claim to detect semantic contradiction from arbitrary prose.

### 6. Rest-cycle separation

`latka_jazn/core/rest_cycle_controller.py`

Rest is now explicitly split into:

`replay -> offline consolidation -> optional dream -> evaluation -> promotion decision`

If the dream model is unavailable but offline consolidation succeeds, the cycle completes as:

- `rest_mode = offline_consolidation_only`;
- `dream_generated = false`;
- `automatic_l3_allowed = false`.

Therefore the runtime can truthfully report model-free rest work without falsely claiming a dream.

### 7. `MemoryPromotionGate`

`latka_jazn/memory/memory_promotion_gate.py`

Synthetic/reflection materialization is no longer controlled solely by a dream evaluator.

The promotion gate checks:

- target tier;
- presence of real source anchors;
- distinct source identity;
- source identity/content-hash conflicts;
- whether the candidate is synthetic.

Invariants:

- automatic long-term/L3 promotion is denied;
- no-source synthetic output is denied;
- conflicting source identity requires review;
- source-anchored synthetic output may become at most an inferred L2 candidate;
- the existing rest shadow mode can still prevent all materialization.

`RestConsolidationGate` invokes this gate before `_materialize_l2()`.

## Truth invariants

### EPI-1 — no self-authenticating dream claim

Generated prose cannot prove that dream computation occurred.

### EPI-2 — no daemon-equals-work shortcut

A running process is not evidence of background work. Recorded event identifiers are required.

### EPI-3 — confidence never upgrades inference to fact

Model confidence is metadata, not provenance.

### EPI-4 — synthetic content never becomes factual evidence for itself

Dream scene hashes may identify a synthetic artifact, but cannot serve as factual support for the scene's own assertions.

### EPI-5 — evidence decisions are auditable

Strong self-claim decisions must leave a hash-chained audit record, not private chain-of-thought.

### REST-1 — consolidation does not require a generative model

Deterministic rest remains useful and testable when DreamSandbox is unavailable.

### REST-2 — dream and rest are separate facts

A completed offline rest cycle with zero scenes does not permit `I dreamed`.

### MEM-1 — automatic L3 promotion from rest is impossible

The contract, promotion gate and rest decision object all reject automatic long-term promotion.

### MEM-2 — conflicts do not self-resolve

A source identity that points at multiple content hashes is flagged for review rather than automatically selecting a winner.

## Regression coverage

The branch contains unit/integration regression tests covering:

- unsupported positive dream claims;
- counts without a verified wake report;
- supported dream claims with verified report metadata;
- truthful negative dream statements;
- daemon-without-events rejection;
- event-count-without-identifiers rejection;
- structured inference remaining inference despite high confidence;
- external factual claims requiring explicit source identifiers;
- evidence collection with missing rest storage;
- hash-chained epistemic ledger validation and tamper detection;
- automatic L3 promotion denial;
- source identity/content conflict review requirement;
- deterministic duplicate detection;
- inferred-only replay not being reported as source-anchored;
- rest-cycle completion without a dream model.

## Explicit non-goals

This branch does not claim to eliminate arbitrary LLM hallucination. It establishes enforceable system-level invariants around claims for which Jaźń has machine-verifiable evidence and introduces a structured route for broader provenance-aware claims.

It also does not update base-model weights during rest. Any future LoRA/fine-tuning subsystem would require its own training dataset provenance, evaluation suite, rollback checkpoint and catastrophic-forgetting tests before being allowed to modify a model.

## Validation boundary

The GitHub branch contains tests, but a green test run must only be claimed after real execution. If the current host cannot obtain a checkout or CI run, the branch remains `implemented, test execution pending` rather than being described as merge-ready.
