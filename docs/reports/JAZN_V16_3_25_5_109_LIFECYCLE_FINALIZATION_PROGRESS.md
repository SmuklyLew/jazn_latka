# v109 lifecycle and finalization progress

Status: IN_PROGRESS. This is an implementation checkpoint, not a release claim.
Baseline: v108 commit bdf9ea1e8131041bf44b2be3cc024915e9b7c736.
Branch: upgrade/v16.3.25.5.109-engine-lifecycle-finalization-decomposition-convergence.

## Phase-2 extraction

FinalizationService now owns the existing validated visible-candidate capture and
append-only persistence path. The host claim, semantic validation, final response
contract, consume and session reconciliation retain their existing order and
fail-closed behavior. Phase-2 no longer constructs or shuts down JaznEngine.
The engine compatibility method delegates to the same service and existing ledger.
Service construction does not open the ledger; rejected binding cannot create it.

Seven existing test modules retain their assertions and now inject the narrow
service instead of the full engine. Their committed v108 bytes are preserved in
`tests/archive/v16.3.25.5.108-finalization-service-seam/`.

Validation at this checkpoint:
- phase-2, MCP, accepted visible turn and continuity regressions: 41 PASS;
- narrow-service and existing engine persistence regressions: 8 PASS;
- changed Python compilation and diff whitespace: PASS;
- full v109 tests, Pyright, release-hardening, cross-platform E2E and cleanroom: NOT RUN.

## Remaining v109 work

- side-effect-free engine construction and RuntimeCompositionRoot;
- explicit build, validation, hydration, startup, cleanup and failure lifecycle;
- stable procedural rule identity and seed migration evidence;
- explicit project-index startup and invalidation reason;
- finalization state/atomicity acceptance beyond unchanged persistence semantics;
- complete version-coupled contracts, release documentation and generated metadata;
- all final-SHA release gates before declaring merge-ready.

No PR may be merged without explicit user approval. No accepted runtime voice or
private MEMORY continuity is implied by these repository tests.
