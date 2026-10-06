# v109 lifecycle and finalization progress

Status: IN_PROGRESS. Baseline: v108 bdf9ea1e8131041bf44b2be3cc024915e9b7c736.
Branch: upgrade/v16.3.25.5.109-engine-lifecycle-finalization-decomposition-convergence.

## Construction and ownership

RuntimeCompositionRoot owns build, validate, hydrate, start and close of the
existing engine services. It does not create another runtime session or daemon.
JaznEngine only binds started services; file hashes before and after binding are
identical in the regression test. A second engine cannot bind the same services.
The main control plane and JaznRuntimeSession retain the composition root and
close it. Partial construction closes acquired stores, and repeated close is safe.
Project index loading/building and engine_started events occur in explicit start.
Cache reuse, missing cache, unreadable cache and root mismatch have distinct reasons.

Procedural seeding is an explicit bootstrap operation. UUID5 identity excludes
release version. Exact legacy rules keep their UUID and original JSONL bytes;
SQLite is reconciled without appending duplicate historical rules. The inventory
separates canonical system rules, two existing memory/profile compatibility rules,
and historical compatibility wording. No historical memory/profile data is deleted.
The two user-specific legacy rules are preserved for compatibility, not inferred
as new user memories. Their future profile migration requires separate evidence.

## Single finalization authority

chat_command_contract routes phase-2 to FinalizationService.finalize through narrow
payload, presentation and settlement ports. No engine, indexer, retrieval, affect,
NLP or model construction occurs on this path. Validation and regeneration remain
fail-closed, with unchanged lineage, timestamp, digest and envelope checks.

The service records candidate_received, binding_verified, candidate_validated,
final_contract_built, persistence_prepared, commit_accepted and visible_accepted.
The pending-store consumed record contains the exact candidate and is the sole
acceptance authority. Candidate preparation does not append an assistant event.
Atomic rename commits acceptance before ledger/conversation/session projections.
A failure before commit leaves no accepted artifact and blocks replay. Projection
failure after commit is explicitly pending_recovery; it does not authorize another
finalization or erase the durable accepted candidate. These tests cover injected
process-level write failures, not a guarantee against every storage power-loss mode.

The legacy engine persistence method delegates to the narrow service. There is no
reverse fallback to full engine construction. Changed active test bytes are archived
under tests/archive before moving only their mock injection points; assertions remain.

## Validation evidence so far

- Initial phase-2 extraction: 49 tests PASS.
- Lifecycle, phase-2, MCP and injected precommit/projection failures: 54 tests PASS.
- Additional duplicate-owner, legacy UUID and code-health checks: 10 tests PASS.
- Pyright: 0 errors, 1 existing unsupported __all__ warning (1091 files).
- compileall: PASS.
- Initial full local run: FAIL, 2058 passed, 3 failed, 6 skipped. Failures were a
  persistent-recall transport timeout, deployment version pin, and generated test
  catalog drift. Pin/catalog are repaired; fresh recall diagnosis is still running.
- Final v109 full suite, CI release-hardening, Linux/Windows E2E, package cleanroom:
  pending. This checkpoint is not merge-ready.

The v108 final SHA has successful manually dispatched Pyright, release-hardening,
package cleanroom and full Windows PowerShell workflows (runs 37399152030,
37399154511, 37399157107, 37399159451). Dedicated persistent E2E runs succeeded on
the preceding code SHA; the metadata-only final SHA full suites include those tests.
PR #318 is unmerged. No merge is authorized.

## Primary references checked 2026-10-06

- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
  Transport bindings preserve core message semantics. A transport connection is
  not the application's session owner or finalization authority.
- https://docs.python.org/3/library/os.html#os.replace
  Same-filesystem replacement is the existing pending-store commit primitive;
  projection writes are not part of that atomic replacement.

Repository work does not imply an accepted runtime voice or private MEMORY recall.
