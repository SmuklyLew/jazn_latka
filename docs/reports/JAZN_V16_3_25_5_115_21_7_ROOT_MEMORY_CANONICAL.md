# Release 16.3.25.5.115.21.7 — canonical ./memory at SYSTEM root

## Accepted operator layout

For a non-versioned local Jaźń installation, `<SYSTEM root>/memory/` (beside `run.py`, `main.py`) is the canonical private MEMORY path. Path selection is independent of shell working directory. Persistent MEMORY data is still **not part of the SYSTEM release archive** or source repo; `.gitignore` and Pack Generator exclusions enforce this.

The operator can override this with `JAZN_MEMORY_ROOT` as a full absolute path. A relative override such as `./memory` is anchored to the SYSTEM root. Relative `..` traversal and cross-platform drive confusion fail closed.

`workspace_runtime` continues as the operational state root, not the new MEMORY root. When the new root has no actual payload, a prior populated `workspace_runtime/memory` is **read-compatible only** until separate authorized migration. Empty placeholders cannot mask older memory. Explicit overrides remain authoritative even if empty.

## Migration and upgrade truth boundary

Changing source code **does not move or reconstruct private data**. Existing deployments with versioned roots must choose an explicit stable `JAZN_MEMORY_ROOT` when continuity across upgrades is needed; otherwise each independently materialized code root has its own `./memory`. This limitation is intentional and must be visible to operators. An operator-controlled migration requires daemon stop, SQLite-consistent snapshot with WAL, source/destination identity and SHA checks, available disk and same-filesystem staging, atomic install/rollback and post-start readiness verification. Never silently overwrite either root.

Backup and failed attach directories are placed under the external operational workspace rather than inside SYSTEM. Attach continues to require an inactive daemon, verified MEMORY package, same-filesystem atomic replacement and fail-closed SQLite gates. An old host root may be moved to backup only as part of an explicitly requested verified attach/convergence.

Changing MEMORY path does **not** establish `full_autobiographical_recall_ready`. Native unified SQLite validation, provenance and memory-readiness gates are unchanged.

## Scope and checks

- Resolver, availability/diagnostics, config studio safety exception, memory attach rollback staging, packaging scanner, generated and source MEMORY attachment contracts, docs and release version.
- Unit coverage for default, relative/absolute override, old-host fallback, empty placeholders, traversal, back-up outside SYSTEM and package exclusions.
- Existing active tests archived byte-exactly under `tests/archive/v16.3.25.5.115.21.6-root-memory-canonical`.
- Validate on GitHub Windows/Linux: stable test contracts, Pyright, release-hardening, package cleanroom, persistent runtime E2E, PowerShell regressions and MEMORY attach gates.

No private SQLite, WAL, ZIP, credentials, or runtime marker is included in this change.
