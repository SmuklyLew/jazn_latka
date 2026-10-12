# Jaźń v16.1.1 — single unified memory runtime

Date: 2026-08-23
Version: `16.1.1-single-unified-memory-runtime`

## Outcome

`memory_jazn.sqlite3` is now the only native LivingMemory runtime database. The
accepted native schema identities are `jazn_unified_memory/v2.4` and its compatible
successor `jazn_unified_memory/v2.5`. The v2.5 successor adds a trigger-maintained
FTS5 index for `memory_records` while retaining the archive, journal and experience
indexes in the same physical database.

The historical five-database layout remains available only as an explicitly
reported read-only compatibility source and migration input. It cannot set
`memory_search_ready=true`, cannot be combined with a selected native database,
and is never presented as a second canonical runtime.

## Truth and readiness gates

Native readiness now requires all of the following:

- a supported schema identity stored in `unified_memory_meta`;
- required unified tables in the same physical database;
- SQLite quick/full integrity and foreign-key checks;
- required FTS objects with source/index row-count agreement and a real MATCH probe;
- bounded, cancellable read probes across memory, experience, journal and archive records.

CLI capability diagnostics consume this gate instead of treating file existence or
conversation-archive status as proof that LivingMemory recall works.

## Recall and provenance

The gateway selects exactly one native database by deterministic discovery order.
All four logical recall layers point to that one file. Recall remains read-only,
bounded and cancellable; it excludes rejected/superseded experience and journal
records, supports earliest/latest ordering, and returns evidence/source identifiers
without promoting source rows or candidates to L3.

## Migration safety

Legacy migration now:

1. snapshots every source with SQLite Backup API, including committed WAL state;
2. validates snapshot integrity and foreign keys;
3. imports into a same-filesystem staging database;
4. rebuilds search indexes and performs full validation;
5. atomically replaces the canonical target only after the stage is valid.

Original sources are never attached or modified. Repeated migration uses stable
keys and `INSERT OR IGNORE`, so it is idempotent and does not duplicate imported
records. A corrupt source or failed validation leaves an existing target unchanged.

## Windows regressions fixed

- SQLite snapshot and inspection connections now close explicitly instead of
  relying on the transaction-only context manager.
- writable connections are URI-aware, allowing an encoded `mode=ro` legacy ATTACH
  on Windows while preserving the source read-only boundary.
- memory package inspection and legacy repack use the canonical encoded read-only
  connector and release file handles deterministically.

## Verification

- focused unified/legacy/migration/Windows gate: `38 passed, 1 skipped`;
- memory-selected suite: `255 passed, 3 skipped`;
- Python compilation: passed; Pyright 1.1.411: `0 errors, 0 warnings`;
- semantic route audit: `132/132`, `ok=true`;
- cognitive architecture audit: all `24` checks true, including `12/12`
  dialogue regressions;
- system package smoke: `14` required checks passed, `ok=true`; the source
  manifest mismatch is the expected optional dirty-development result;
- first full Windows/Python 3.12 run: `838 passed, 5 skipped, 2 failed`.
  The failures exposed a POSIX-only test collected on Windows and a real status
  regression: after `/live` was split from readiness, CLI status still expected
  readiness fields in the liveness payload. The test is now platform-skipped and
  status performs an explicit bounded `/ready` probe. Exact reruns finish as
  `1 passed, 1 skipped`; the final convergence run repeats the entire suite.

No private memory database, private export, registry, workspace-runtime marker,
SQLite sidecar, WAL/SHM file or generated package is part of this release commit.
