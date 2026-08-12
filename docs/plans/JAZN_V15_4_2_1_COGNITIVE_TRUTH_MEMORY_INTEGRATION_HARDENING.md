# Jaźń v15.4.2.1 — Cognitive Truth & Memory Integration Hardening

**Target:** `v15.4.2.1-cognitive-truth-memory-integration-hardening`  
**Baseline:** `v15.4.2.0-rest-replay-dream-continuity`  
**Release character:** corrective integration hardening; no new consciousness claim  
**Primary rule:** a capability is not `working` merely because a module exists, imports, or passes an isolated unit probe.

## 1. Why this release exists

A live audit of v15.4.2.0 found a class of **false-green integration states**. Individual modules and tests were real, but several system-wide claims were stronger than the observed execution path justified.

The audit identified four P0 failures/gaps:

1. a recovered memory snapshot could also become the ordinary runtime write target, so accepted turns changed the source fingerprint used by normalization and could make a freshly built wake-state stale;
2. a wake-state could be built through a shortened/manual recovery path even when the canonical conversation archive was not fully searchable because FTS/staging shards were absent;
3. RestReplay read primarily from the tier store, where a restored runtime could expose only one aggregated wake item instead of the individually normalized source-grounded memories;
4. the rest scheduler could be healthy while DreamSandbox had no eligible local autonomous model, but readiness did not make the distinction sufficiently explicit.

The same audit found P1 integration gaps:

- `KnowledgeFabric` and `LexicalIntelligenceEngine` existed and had unit tests but were not on the actual `JaznEngine` turn path;
- homeostasis/prediction outputs were primarily reported as telemetry instead of producing observable bounded control effects;
- architecture audits could report green capability status from file presence plus isolated probes;
- top-level runtime readiness was too easy to read as cognitive/memory readiness.

P2 findings covered scientific-source metadata: two source keys referenced by the neuropsychology map did not resolve, and the CLIN entry had an incorrect title despite a valid source link.

This release treats those findings as **truth-contract defects**, not cosmetic documentation issues.

## 2. Evidence model: what “works” means

v15.4.2.1 introduces a stricter evidence vocabulary for capability claims:

1. `present` — implementation artifact exists;
2. `constructible` — it can be instantiated with valid dependencies;
3. `callable` — its public contract executes;
4. `reachable_from_turn` — the ordinary runtime path invokes it;
5. `effect_observed` — disabling/changing it creates an expected, bounded behavioral difference;
6. `persistence_verified` — when it claims durable state, that state survives readback and integrity checks;
7. `live_verified` — the active runtime has exercised the capability with real configured dependencies.

Only behavioral evidence should justify `working`/`ready` language. A file-presence audit may report `present_unverified`, never `working`.

This follows the engineering lesson from cognitive-agent architectures such as CoALA: useful capability requires memory, action space and a decision process that actually selects actions, not a list of modules. Generative Agents similarly used ablation to show that observation, reflection and planning made measurable contributions rather than treating component presence as sufficient evidence.

Primary sources:

- Sumers et al., *Cognitive Architectures for Language Agents (CoALA)*: https://arxiv.org/abs/2309.02427
- Park et al., *Generative Agents: Interactive Simulacra of Human Behavior*: https://arxiv.org/abs/2304.03442

## 3. Non-goals and scientific boundary

v15.4.2.1 does **not**:

- claim a biological nervous system, biological homeostasis, sleep, dreaming, consciousness or subjective experience;
- add automatic model-weight updates or fine-tuning from private memory;
- make a remote model eligible for autonomous DreamSandbox execution;
- make rest health a prerequisite for ordinary dialogue;
- auto-promote synthetic rest output to L3;
- replace canonical L0 source archives with generated summaries;
- weaken source provenance, finalization, tool authorization or package integrity.

Terms such as “homeostasis”, “neurocognitive”, “replay” and “wake” remain engineering analogies. Their implementation must be described by actual software behavior.

## 4. P0-A — immutable recovery source vs mutable runtime writes

### Defect

After recovery, `memory_db_path` could resolve to `recovery_current/runtime_memory_recovered.sqlite3`. The same file was also treated as the normalization source. Ordinary accepted turns therefore mutated the source snapshot and could cause `source_changed` immediately after a valid wake build.

### Corrected ownership

v15.4.2.1 separates paths in `JaznConfig`:

- `normalization_source_db_path` — read-only recovery snapshot when available;
- `runtime_write_db_path` — mutable runtime write database;
- `memory_db_path` — mutable write target;
- `memory_db_path_readonly` — read-only URI for the mutable write target.

The recovered snapshot is no longer the ordinary write target.

### Invariants

- recovery source may be fingerprinted repeatedly without accepted-turn writes changing it;
- ordinary runtime persistence must not write into `recovery_current/runtime_memory_recovered.sqlite3`;
- normalization can still use the recovered source as immutable material;
- fallback installations without recovery keep a valid runtime-write path.

### Required regression

`test_recovery_snapshot_is_not_runtime_write_target` verifies both paths exist conceptually and are distinct after recovery.

## 5. P0-B — searchable conversation archive is a wake prerequisite

### Defect

A shortened/manual restore could publish conversation data but omit canonical `staging_v1` or FTS shards. SQLite integrity could still be green, yet `ready_for_search=false`. Building full wake from such a state overstates practical recall readiness.

### Correction

`MemoryRecoveryPipeline` now examines the canonical `conversation_archive_v1` manifest before normalization/wake. When a canonical archive is present (recognized by current manifest tables), it must satisfy `ConversationArchiveStore.status().ready_for_search`.

If not, recovery returns:

- `status=archive_not_searchable`;
- archive issues/reasons;
- no verified wake publication.

Legacy/synthetic fixtures without the current canonical manifest schema remain backward compatible and are not falsely rejected as current archives.

### Operator implication

The verified restore path remains:

`L0/Test04 → archive + staging + FTS → recovery source → normalization → wake`.

A host/manual shortcut that omits FTS/staging is no longer allowed to produce a full-success wake result.

## 6. P0-C — RestReplay reads individual normalized source records

### Defect

v15.4.2.0 RestReplay selected from `MemoryTierStore`. After wake hydration the tier DB could contain only one aggregate wake item. The algorithm itself was correct on synthetic unit fixtures, but the live restored system lacked diverse replay inputs.

### Correction

`RestReplayEngine` now has a bounded read-only path to the normalization sidecar.

It selects only from the **latest successful full-coverage normalization run** and reads individual `normalized_memory_items` with their source identity/provenance. It does not treat a partial run as authoritative.

Candidate evidence includes where available:

- normalized item ID;
- source table and row ID;
- conversation/message identifiers;
- source file/source identifier;
- source/content SHA;
- normalization run ID;
- truth/memory kind mapping;
- evidence metadata.

The engine merges normalized candidates with existing tier candidates, preserves diversity/anti-loop scoring and applies a penalty to aggregate wake records so one aggregate cannot monopolize replay.

### Safety

- sidecar access is read-only;
- no replay operation mutates source memory;
- unsupported truth classes remain excluded;
- a normalized synthetic/inferred item still does not become an independent real-source anchor unless its truth/provenance contract permits it.

### Required regression

An integration fixture with three distinct normalized items must return multiple individual source IDs instead of a single aggregate wake item.

## 7. P0-D — scheduler readiness and dream readiness are separate

### Defect

A live RestCycleController can schedule, persist and report cycles while DreamSandbox has no eligible autonomous local generator. Treating this as one `rest_ready` concept makes an idle scheduler look like an active dream generator.

### Correction

`DreamSandbox.readiness()` explicitly reports generator eligibility. `RestCycleController.status_payload()` exports separately:

- `rest_scheduler_ready`;
- `rest_scheduler_running`;
- `rest_dream_ready`;
- `dream_readiness` with reason/provider boundary.

An injected deterministic generator used by tests can be ready; a null/remote/host-only adapter cannot.

### Truth rule

If `rest_scheduler_ready=true` and `rest_dream_ready=false`, the visible system may claim a functioning idle scheduler/ledger but **must not claim that synthetic dream scenes are being generated**.

## 8. P1-A — KnowledgeFabric moves onto the real turn path

### Previous state

The module and tests existed, but the ordinary engine did not instantiate/use it.

### Integration

`JaznEngine` now constructs `KnowledgeFabric` as an evidence-layer wrapper. To avoid introducing a second autobiographical database, the integration can transform memory evidence that has already passed existing memory/truth gates.

`KnowledgeFabric.evidence_from_memory_context()` can wrap bounded authorized evidence from:

- conversation archive hits;
- living-memory hits;
- source-file hits;
- legacy messages;
- episodic records.

Each result preserves locator/provenance, confidence, search pass and content hash where available.

The resulting packet is attached to the cognitive frame and model-guided generation context with `runtime_integrated=true`.

### Invariant

KnowledgeFabric does not bypass memory truth gates and does not silently create a parallel identity/memory source.

## 9. P1-B — Lexical Intelligence moves onto the real turn path

### Previous state

`LexicalIntelligenceEngine` existed and passed its own tests but was not invoked by the engine.

### Integration

`JaznEngine` now owns a lexical engine backed by a rebuildable cache under `workspace_runtime`. For each bounded turn it analyzes only a small set of focus/keyword terms and adds a lexical-evidence packet to the cognitive frame/model context.

Optional providers remain fail-soft. Lack of Morfeusz/plWordNet/network resources must not block ordinary Polish dialogue.

### Invariant

Lexical results are evidence, not authoritative semantic truth and not autobiographical memory.

## 10. P1-C — homeostasis obtains a measurable bounded control effect

### Previous state

`HomeostasisRegulator` produced useful diagnostics such as `generation_limit`, but downstream execution did not enforce a clear effect.

### Integration

`CognitiveRuntimeCoordinator` now exports a compact `control_effects` contract containing bounded values such as:

- `generation_limit`;
- `max_tool_calls`;
- verification/confirmation requirements;
- action state;
- explicit marker that predictive output is advisory.

`runtime_turn_contract` enforces `generation_limit` by mapping it into `ModelAdapterRequest.max_output_tokens`, with a hard safe clamp. Metadata records `cognitive_control_enforced`.

This creates a real closed segment:

`state/conflict → homeostatic plan → control_effect → model request budget`.

### Boundary

This is still software regulation, not biological homeostasis. Prediction remains advisory until a separately tested control path consumes it.

## 11. P1-D — truthful diagnostic readiness dimensions

A single `doctor.ok` is retained as process/install health, but v15.4.2.1 exposes separate capability dimensions so it cannot reasonably be read as “all cognition healthy”:

- `runtime_ready`;
- `memory_search_ready`;
- `continuity_ready`;
- `rest_scheduler_ready`;
- `rest_dream_ready`;
- cognitive integration status.

The payload states explicitly that process readiness is not equivalent to memory, continuity, dream-generation or cognitive-integration readiness.

## 12. P1-E — architecture audits must prove integration, not file presence

### Cognitive architecture audit

The independent audit keeps existing checks and adds source/behavior probes for:

- KnowledgeFabric reachable from turn code;
- Lexical Intelligence reachable from turn code;
- RestReplay normalized-source path;
- recovery/write path separation;
- homeostatic generation limit enforced in model request construction;
- bounded KnowledgeFabric evidence transformation;
- lexical engine execution;
- DreamSandbox readiness distinction.

### SelfArchitectureAuditor

Existence-only capabilities now report `present_unverified`, not `ok`. `working_capabilities` is reserved for behavior-verified entries.

The audit must not upgrade a capability from presence to working simply because all files exist.

## 13. P2 — scientific-source integrity

v15.4.2.1 fixes three metadata defects:

1. `pmc_interacting_brain_systems_memory_consolidation` now resolves to the review *Interplay of hippocampus and prefrontal cortex in memory* (Preston & Eichenbaum): https://pmc.ncbi.nlm.nih.gov/articles/PMC3789138/
2. `pmc_hippocampus_prefrontal_amygdala_learning_memory` now resolves to the relevant PMC source on hippocampus/prefrontal cortex/amygdala interactions;
3. CLIN metadata uses the correct title *CLIN: A Continually Learning Language Agent for Rapid Task Adaptation and Generalization*: https://openreview.net/forum?id=8wgNZ7Kado

Scientific references are provenance for design analogies. A source link never proves biological equivalence of the software component.

## 14. Operational anti-regression lesson

The release adds a verified operational lesson for false-green capability reporting:

- trigger: capability reported working from module/file presence;
- expected behavior: require behavioral reachability/effect evidence;
- root cause: presence-based audit semantics;
- repair rule: distinguish presence, integration and live verification;
- regression: `tests/test_cognitive_truth_memory_integration_v15421.py`.

## 15. Test matrix

### New dedicated tests

`tests/test_cognitive_truth_memory_integration_v15421.py` verifies:

1. recovered snapshot is not the runtime write target;
2. RestReplay reads multiple individual normalized records;
3. Dream readiness distinguishes absent generator from a ready injected generator;
4. homeostatic generation limit reaches the actual model request;
5. KnowledgeFabric wraps already-authorized runtime memory evidence;
6. scientific source keys resolve and CLIN title is correct;
7. existence-only self-architecture checks do not become behavior-verified;
8. canonical non-searchable archive blocks wake recovery.

### Existing gates retained

No existing release gate is removed:

- compileall;
- Pyright;
- semantic-route audit;
- cognitive-architecture audit;
- full deterministic pytest (`not live_model and not live_mcp`);
- targeted Windows runtime/path suite;
- package/provenance metadata sync;
- clean checkout guard;
- post-merge release/package smoke.

The Windows targeted suite includes the v15.4.2.1 integration regressions.

## 16. Acceptance criteria

The release is ready to merge only when all are true:

- runtime-write and recovery source are distinct under recovered-memory configuration;
- canonical archive missing FTS/staging cannot yield verified wake success;
- sidecar-backed RestReplay returns multiple individual source-grounded records in integration tests;
- `rest_dream_ready=false` without eligible local model and true only with a verified eligible generator;
- KnowledgeFabric and Lexical Intelligence are reachable from ordinary engine turn construction;
- a homeostasis output causes an observable bounded change in the model request;
- presence-only architecture checks do not report `working`;
- all referenced neuro/scientific source keys resolve;
- deterministic tests, Pyright and CI are green;
- canonical metadata is generated by release workflow, not edited by hand;
- PR head is merged with an expected-head guard after synchronized CI.

## 17. Rollout after merge

1. Build a new system package from synchronized `master`.
2. Bootstrap v15.4.2.1 into a new versioned root.
3. Use the canonical verified-memory restore path, including archive, staging and FTS.
4. Confirm `memory_search_ready=true` before calling recall healthy.
5. Confirm wake freshness after normal accepted-turn writes.
6. For rest/dream tests, provision a genuinely local eligible model; otherwise expect scheduler-only behavior.
7. Run live ablation/effect probes before promoting additional cognitive modules to `live_verified`.

