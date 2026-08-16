# Epistemic and Rest Consolidation Hardening

## Scope

This change hardens two failure classes that directly affect runtime truthfulness:

1. strong self-claims such as "I dreamed" or "I worked in the background" must not be emitted without structured runtime evidence;
2. useful idle/rest work must not collapse merely because a local generative model is unavailable.

The implementation is intentionally narrower than a generic LLM fact checker. It adds deterministic invariants that the runtime can actually verify.

## Research basis

### Offline replay and consolidation

Tadros et al., *Sleep-like unsupervised replay reduces catastrophic forgetting in artificial neural networks*, Nature Communications 13, 7742 (2022), DOI: 10.1038/s41467-022-34938-7.

The paper demonstrates a sleep-like offline replay phase that reactivates previously learned representations and reduces catastrophic forgetting. The important engineering implication for Jaźń is that replay/consolidation is a distinct operation from natural-language dream generation.

Primary source: https://www.nature.com/articles/s41467-022-34938-7

### Generative replay

Shin et al., *Continual Learning with Deep Generative Replay* (2017), arXiv:1705.08690.

Generative replay interleaves generated samples representing older tasks with new-task learning. Generated samples are a mechanism for replay; they are not evidence that a real-world event occurred.

Primary source: https://arxiv.org/abs/1705.08690

### Stability/plasticity and protection of previous knowledge

Kirkpatrick et al., *Overcoming catastrophic forgetting in neural networks* (2016/2017), arXiv:1612.00796.

Elastic Weight Consolidation shows that continual learning needs explicit protection for previously acquired knowledge. This supports treating consolidation as a controlled mechanism rather than unrestricted self-modification.

Primary source: https://arxiv.org/abs/1612.00796

### Imagination/world-model simulation

Hafner et al., *Mastering Diverse Domains through World Models* (DreamerV3), arXiv:2301.04104.

DreamerV3 improves behavior through imagined future trajectories inside a learned world model. For Jaźń this is an analogy for a sandboxed generative phase, not a basis for representing generated scenes as observed facts.

Primary source: https://arxiv.org/abs/2301.04104

### Retrieval, factuality and provenance

Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, arXiv:2005.11401.

The paper motivates combining parametric generation with explicit non-parametric memory, including provenance and updatable knowledge. Retrieval improves factuality but does not itself prove every generated claim.

Primary source: https://arxiv.org/abs/2005.11401

### Model self-evaluation is useful but insufficient as a truth gate

Kadavath et al., *Language Models (Mostly) Know What They Know*, arXiv:2207.05221.

Language models can exhibit useful calibration and self-evaluation, but calibration does not generalize perfectly across tasks. Therefore Jaźń must not use model confidence as the sole authority for runtime truth.

Primary source: https://arxiv.org/abs/2207.05221

### Truthfulness cannot be assumed from scale or fluent generation

Lin, Hilton, Evans, *TruthfulQA: Measuring How Models Mimic Human Falsehoods*, arXiv:2109.07958.

The benchmark demonstrates that fluent language models can reproduce common falsehoods. Runtime truthfulness therefore needs external constraints and evidence, not only prompting.

Primary source: https://arxiv.org/abs/2109.07958

## Implemented invariants

### EPI-1: dream claims are fail-closed

A positive visible statement equivalent to "I dreamed" requires structured evidence:

- `rest_cycle_count > 0`, and
- `dream_scene_count > 0` or a non-empty `dream_scene_ids` collection.

Without those fields the visible reply capture raises `EpistemicClaimViolation`.

A negative statement such as "I did not dream" does not require positive evidence.

### EPI-2: background-work claims are fail-closed

A positive visible statement equivalent to "I worked in the background" requires:

- `daemon_verified == true`, and
- `background_event_count > 0`.

A running daemon by itself is not evidence that work occurred.

### EPI-3: evidence is structured, not inferred from prose

The guard does not accept phrases such as `cycle_count=1` embedded in model-generated prose as proof. Evidence must be passed separately to the final capture API.

### REST-1: replay/consolidation does not require DreamSandbox

Every eligible rest cycle now performs deterministic offline consolidation before attempting dream generation.

The offline pass checks:

- replay item count;
- real source anchor count;
- inferred/symbolic item count;
- content hash integrity;
- basic provenance presence;
- exact duplicate content groups;
- truth-status distribution.

It does not invent semantic relations or facts.

### REST-2: absence of a dream model no longer makes the whole cycle `skipped`

If the offline pass succeeds and `DreamSandbox.generate()` returns no scene, the cycle is completed with:

- `rest_mode = offline_consolidation_only`;
- `dream_generated = false`;
- the dream diagnostic reason preserved;
- `automatic_l3_allowed = false`.

This means the system can truthfully report that rest/consolidation work happened while separately reporting that no dream scene was generated.

### REST-3: synthetic scenes remain non-factual

Existing `DreamScene.factual_claim_allowed == False` and the prohibition on automatic L3 promotion remain unchanged.

## Non-goals

This change does **not** claim to solve arbitrary hallucinations. It deliberately avoids a misleading generic `TruthChecker` that would itself depend on unverified model judgment.

It also does not train or fine-tune the base LLM during rest. Offline consolidation currently operates on persistent memory records and audit metadata only.

## Regression requirements

Tests must prove that:

- unsupported dream claims fail closed;
- supported dream claims require event evidence;
- negative dream statements remain allowed;
- unsupported background-work claims fail closed;
- daemon presence without recorded events is insufficient;
- offline rest works with no dream generation;
- exact duplicate detection is deterministic;
- inferred-only replay cannot be reported as source-anchored;
- empty replay is a completed housekeeping pass, not fabricated cognition.
