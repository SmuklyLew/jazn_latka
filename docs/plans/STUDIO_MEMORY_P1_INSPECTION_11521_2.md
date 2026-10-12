# P1 Memory Studio: source, target, staging, host-selected MEMORY — 16.3.25.5.115.21.2

Parent: `upgrade/v16.3.25.5.115.21.1-test-studio-history-p1` (PR #345). Separate Draft PR; do not merge before parents. This is **partial P1**, not full Studio modernization.

## Contract

- Source inventory is a bounded filesystem metadata check of enabled project sources, never a private-content read or approval.
- The selected target and one unambiguous canonical `memory/.rebuild_staging/<run-id>/sqlite/memory_jazn.sqlite3` candidate are inspected through the existing native read-only SQLite schema/identity probe. More than 32 staging entries, symlinks, incomplete WAL sidecars, malformed or foreign schemas fail closed.
- Host-selected MEMORY is resolved only via the project's canonical `resolve_memory_root_diagnostic`; it is **not** proven active, ready for recall or equal to the target.
- Report does not expose source contents or private absolute paths. It never reads private prompts or extracts raw MEMORY.
- All activation/publication/continuity claims stay fail-closed (`false`/`null`). No backup, import, migration, transaction, copying, SQLite writes or daemon restart.
- Existing Studio database page adds the report through its current action dispatcher, not a second GUI or lifecycle owner.

## Tests and acceptance

`tests/test_memory_studio_p1_inspection.py` uses synthetic files and SQLite fixtures to test absence, contamination, foreign schema, staging ambiguity, host selection and symlink guards. Changed release-pinned tests are archived byte-for-byte under `tests/archive/v16.3.25.5.115.21.1-pre-memory-inspection-p1/`.

Required: targeted pytest, full deterministic suite, Pyright, compileall, Windows/Linux CI, Test Studio catalog sync and canonical release metadata. This patch does **not** perform real-host MCP accepted-turn validation.

Official SQLite guidance: https://www.sqlite.org/uri.html and https://www.sqlite.org/pragma.html. Schema integrity does not prove lineage or activation readiness.
