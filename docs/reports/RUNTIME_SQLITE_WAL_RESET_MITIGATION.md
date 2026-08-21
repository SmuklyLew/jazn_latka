# Runtime SQLite WAL-reset mitigation

## Problem

A live v15.4.2.1.3 runtime running Python SQLite 3.46.1 developed a corrupted audit shard after WAL/SHM handles diverged from the files visible on disk. The audit shard failed `PRAGMA quick_check`; the runtime-memory shard was healthy once the daemon was stopped. The canonical audit-only repair preserved the failed audit shard and published a healthy replacement.

SQLite documents a WAL-reset corruption race affecting WAL databases on versions 3.7.0 through 3.51.2 unless a documented fixed backport is used. The bug requires multiple connections in separate threads/processes that write or checkpoint at the same time. SQLite 3.51.3 and later contain the fix; fixed backports include 3.50.7 and 3.44.6.

## Change

`connect_runtime_writable()` no longer unconditionally enables WAL. The runtime now selects:

- `WAL` when `sqlite_wal_reset_fix_available()` recognizes a fixed SQLite build;
- `DELETE` rollback-journal mode on affected or unknown builds.

The existing cross-process file lock plus process-local `RLock` remains defense in depth, but is no longer presented as a substitute for the SQLite fix. Runtime capability diagnostics expose the selected journal mode and whether the fallback mitigation is active.

## Safety boundary

This does not repair already-corrupted databases automatically. Storage mutation remains quiescent-only, audit rollover remains non-destructive, and runtime memory rollover still requires explicit `--include-memory`. Upgrading the Python/SQLite runtime to a fixed SQLite remains preferred.

## Verification target

Regression coverage checks the fixed/backport version matrix, journal-mode selection, capability reporting, write/read integrity and concurrent runtime-memory writers.

## Primary source

SQLite, “Write-Ahead Logging”, section “The WAL-Reset Bug”: https://www.sqlite.org/wal.html
SQLite release 3.51.3: https://www.sqlite.org/releaselog/3_51_3.html
