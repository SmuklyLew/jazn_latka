# Jaźń v15.4.0.0 — implementation report

**Target source release:** `v15.4.0.0-cognitive-architecture`
**Baseline:** v15.1.0.3.99 source line
**Status at report creation:** implementation complete locally; canonical release metadata intentionally pending GitHub `manifest_sync`.

## Implemented capability areas

### Dialogue/task continuity

- Added structured `DialogueTaskState` and resolver.
- Extended classifier/context carryover to use active goal/route/task state before loose ellipsis/fallback rules.
- Added safe route for unresolved contextual continuation.
- Corrected eventive Polish expressions such as `działo się` so relationship/history questions are not confused with runtime health/status language.
- Added exact regressions for the production failures around `archiwum rozmów` and `Zrób to wszystko sama...`.

### Reasoning orchestration

- Added fast/standard/deliberative operational lanes.
- Added explicit retrieval/tool/verification/alternative-plan gates.
- Runtime recomputes the final reasoning plan from the **current resolved task and route**, rather than only previous-turn state.
- No hidden chain-of-thought storage or exposure is required by the architecture.

### Knowledge Fabric

- Added bounded, provenance-preserving retrieval API over existing hybrid retrieval capabilities.
- Default sparse path remains SQLite FTS5/BM25.
- Vector/global/relation retrieval remains optional and conditional.
- Command/noise words are removed from generated FTS queries to reduce retrieval failures.

### Polish lexical intelligence

- Added source-aware lexical evidence and rebuildable SQLite cache.
- Upgraded local plWordNet provider from placeholder to a read-only provisioned-index contract.
- Integrated plWordNet into the existing external dictionary adapter even when network access is disabled.
- Preserved built-in NLP when Morfeusz/plWordNet/corpus resources are absent.
- Added a versioned lexical resource catalog with redistribution/license boundaries.

### Verified operational learning

- Added source-controlled anti-regression lesson model.
- Lessons require verified status and can reference deterministic regression tests.
- Runtime can attach a small set of relevant verified lessons to the cognitive frame.
- Lessons cannot modify source autonomously and are not autobiographical memory.

### Host-finalized session continuity

- Added optional continuity commit hash to pending ChatGPT host requests.
- Phase 1 records a pre-turn snapshot without pretending the unfinalized answer was visible.
- Phase 2 advances durable user/assistant/task state only after accepted visible finalization.
- A delayed finalizer cannot overwrite a newer session state.
- Legacy pending records remain compatible.

### Architecture/release hardening

- Added independent `cognitive_architecture_audit`.
- Added deterministic v15.4 dialogue benchmark resource.
- Added v15.4 targeted tests to Windows CI.
- Added cognitive architecture audit to Ubuntu CI without removing semantic audit, Pyright, compileall or full deterministic pytest.
- Updated README architecture description while preserving `latka_jazn/version.py` as the sole current-version source.

## Bugs/regressions found during implementation and fixed

1. **Positive-feedback precedence:** `Dobrze, to kontynuuj.` was consumed as feedback before structured task continuation. Structured task resolution now runs first.
2. **Relationship-history ambiguity:** `Co wtedy działo się między nami...` could miss memory-recall intent. Domain evidence now recognizes this as conversation-history recall.
3. **FTS query noise:** command words could make a valid retrieval query brittle. Knowledge Fabric now normalizes query terms before FTS.
4. **Current-turn planning gap:** preliminary cognitive planning used prior task state. Final reasoning plan is now recomputed after current route/task resolution.
5. **Engine hotspot growth:** initial integration exceeded code-health function-size budgets. New stages were extracted into focused helpers instead of raising the budgets.
6. **Version-current fixture drift:** after the release bump, two test fixtures contained obsolete raw distribution-version literals. They now derive the current distribution version where appropriate.
7. **Local provenance test environment:** the synthetic validation repository had no `origin` URL; local validation was given the canonical repository URL without changing source behavior.

## Local validation completed

- `compileall`: passed.
- v15.4 + host/routing targeted tests: passed.
- full non-live deterministic tests run in four bounded chunks: **654 passed, 3 skipped**.
- code-health regression budgets: passed after helper extraction.
- independent semantic route audit: passed.
- independent cognitive architecture audit: passed, including **10/10** dialogue regressions and verified operational lessons.
- `git diff --check`: passed.
- local Pyright: not installed in this environment; GitHub release-hardening remains the authoritative required static-type gate.
- version consistency: no raw current-version violations remain; only canonical generated metadata is stale locally, intentionally awaiting `release_metadata_sync`.

## Release gate still required

The branch must not be merged on local results alone. Required next gates are:

1. push source changes to the dedicated upgrade branch;
2. canonical GitHub `manifest_sync` regenerates `SOURCE_PROVENANCE.json` and `PACKAGE_INTEGRITY_MANIFEST.json`;
3. synchronized PR CI passes Ubuntu compileall, Pyright, semantic audit, cognitive audit and full deterministic pytest;
4. Windows targeted runtime/path/v15.4 suite passes;
5. branch is current with `master` and mergeable;
6. merge with an expected-head SHA guard;
7. post-merge `master` release-hardening and release package smoke pass.
