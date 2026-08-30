# Jaźń v15.4.2.1 — Cognitive Truth & Memory Integration Hardening implementation report

**Target:** `v15.4.2.1-cognitive-truth-memory-integration-hardening`

## Summary

This corrective release addresses false-green integration states found during a live audit of v15.4.2.0. The central change is epistemic/operational: a capability is no longer considered working merely because the implementation file exists or an isolated unit probe passes.

## P0 fixes implemented

### Recovery source no longer doubles as runtime-write target

`JaznConfig` now separates immutable/normalization recovery source paths from mutable `runtime_write_v1`. Normal accepted-turn persistence therefore no longer mutates `recovery_current/runtime_memory_recovered.sqlite3` simply because recovery exists.

### Canonical archive readiness gates wake recovery

`MemoryRecoveryPipeline` checks current canonical conversation-archive readiness before normalization/wake. A current archive with missing/invalid FTS or staging returns `archive_not_searchable` instead of a false full-success wake state. Legacy/synthetic fixtures without the current archive manifest schema remain compatible.

### RestReplay reads individual normalized records

`RestReplayEngine` now reads a bounded candidate set from the most recent successful full-coverage normalization run in the sidecar, preserving source identifiers/hashes and merging them with tier candidates. Aggregate wake records receive a penalty and cannot be the only practical replay source when individual normalized records exist.

### Dream readiness is explicit

`DreamSandbox.readiness()` and RestCycle status separate scheduler readiness/running state from eligible autonomous model readiness. A healthy scheduler with null/host-only/remote model correctly reports `rest_dream_ready=false`.

## P1 integration fixes implemented

### KnowledgeFabric

`JaznEngine` now owns and invokes KnowledgeFabric on the ordinary cognitive-frame path. It wraps bounded memory evidence that has already passed existing source/memory gates rather than introducing a second autobiographical store. The packet reaches model-guided generation context.

### Lexical Intelligence

`LexicalIntelligenceEngine` is now instantiated by `JaznEngine`, applied to a bounded set of focus terms and included in cognitive/model context. Optional providers stay fail-soft.

### Homeostatic control effect

`CognitiveRuntimeCoordinator` exports bounded `control_effects`; `generation_limit` is enforced as `ModelAdapterRequest.max_output_tokens` with a safety clamp and metadata marker. Prediction remains explicitly advisory.

### Readiness semantics

Runtime diagnostics expose separate capability readiness dimensions for process, memory search, continuity, rest scheduler and Dream generation. The payload states that runtime/process readiness is not equivalent to complete cognitive readiness.

### Architecture audits

`cognitive_architecture_audit` adds reachability and behavior checks for the new integration points. `SelfArchitectureAuditor` reports existence-only modules as `present_unverified`; they no longer populate `working_capabilities` merely from file presence.

## P2 source fixes

- two previously unresolved neuropsychology source keys now resolve in `scientific_basis.py`;
- CLIN uses the correct publication title and existing primary-source URL.

## Regression coverage

New `tests/test_cognitive_truth_memory_integration_v15421.py` covers eight integration/truth defects:

1. immutable recovery vs runtime write ownership;
2. multi-record normalized RestReplay;
3. Dream readiness separation;
4. homeostatic generation-limit enforcement;
5. KnowledgeFabric authorized evidence wrapping;
6. scientific-source resolution/CLIN metadata;
7. presence-only self-audit truth boundary;
8. canonical archive-not-searchable recovery block.

Existing recovery, rest, wake, host-finalization, routing, code-health and package tests remain enabled.

## Local validation before publication

Before the final branch publication step, the implementation passed:

- dedicated v15.4.2.1 tests;
- targeted memory/rest/host/routing regressions;
- `compileall`;
- semantic route audit;
- cognitive architecture audit with 24 checks;
- deterministic suite partitioned to fit the execution window: **699 passed, 3 skipped, 0 failed** on the code state before final documentation-only edits.

A final deterministic rerun is required after all release/documentation/workflow edits. Pyright is not installed in the local execution image and therefore remains an authoritative GitHub `release-hardening` gate; it is not replaced by a weaker local substitute.

## Release truth

`implemented` means source behavior exists. `runtime_integrated` means the ordinary turn path reaches it. `live_verified` requires an active runtime with the actual dependency/configuration. In particular, v15.4.2.1 improves Dream readiness reporting but does **not** provision an Ollama/llama.cpp model by itself.
