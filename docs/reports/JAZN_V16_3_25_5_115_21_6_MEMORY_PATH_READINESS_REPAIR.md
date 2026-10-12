# Jaźń v16.3.25.5.115.21.6 — MEMORY shard paths and readiness

## Diagnosis

During MEMORY v2-to-v3 convergence, validation reported two required SQLite shard paths under memory/memory/sqlite instead of memory/sqlite. The active transactional tier was readable, but the operation ended with a validation failure and did not establish full autobiographical recall.

The SQLite shard manager already handled some legacy memory prefixes, but the independent large-memory validator did not. On POSIX, Windows-style backslashes were additionally interpreted as literal filename characters by the shard manager.

## Fix

- Normalize the historical optional memory/ prefix exactly once against the canonical host-level memory root.
- Interpret portable Windows and POSIX separators consistently in both the runtime shard manager and large-memory validation.
- Reject traversal, drives, UNC roots and duplicated memory/memory prefixes without fabricating shard files.
- Expose malformed JSON, duplicate IDs, missing active shard, and invalid paths in manifest_issues; never return validation ok=true if these errors exist.
- Add synthetic cross-platform regressions. Preserve old active tests byte-exactly in tests/archive before adjusting release-version expectations.
- Synchronize version, startup and MCP deployment contracts to v16.3.25.5.115.21.6.

## Explicitly separate task: autobiographical source reconstruction

The attached historical MEMORY package does not contain a verified native unified schema (unified_memory_meta). A patch to shard path resolution **does not** transform legacy records into a native unified autobiographical database and must not set full_autobiographical_recall_ready=true.

Operator recovery requires immutable source snapshots and SHA-256 lineage, an approved Memory Rebuild Studio project with real Test04 benchmark, the canonical Test00 through Test04 and final validation, SQLite integrity_check / foreign_key_check / FTS checks, review of source conflicts and manual promotion policy, and a separately authorized atomic native-unified deployment. If any gate is missing, readiness remains ready_transactional_tier_only or otherwise degraded.

The historical package and private databases must not be committed to this repository. Synthetic unit-test success or passing CI is not evidence that private autobiographical memory was recovered.

## Validation

Run focused shard-path and memory tests, full deterministic pytest, active-source compileall, Pyright, doctor, package-smoke and mandatory Ubuntu/Windows GitHub CI on the final PR HEAD. The project includes immutable historical test archives, including pre-existing syntax-invalid snapshots: do not change archived source to manufacture a green compileall result.
