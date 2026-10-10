# P1 Memory Provenance & Comparison — 16.3.25.5.115.21.3

Stacked on PR #346, branch 115.21.2. Draft only; no private-memory mutation or merge.

## Evidence model

The P1 inspector remains the structural preflight. Comparison runs only against
verified native-unified SQLite databases. Each source is opened read-only and
copied using the SQLite Online Backup API to a private, isolated temporary
directory outside SYSTEM/MEMORY (contains sensitive transient snapshots).
Snapshots are individually transactionally consistent but NOT simultaneous.
All snapshots and the hashed temporary index are removed at the end.

A streaming SQLite index stores only SHA-256 key and content digests, not raw
record text. It uses the canonical Test04 table list and volatile-column policy
from `test_profiles.py`, but emits an explicitly distinct P1 fingerprint
contract. Aggregate per-table added/removed/changed record-key counts are shown
without record identifiers, text, or paths. Table shape differences are
`incompatible`, absent or unsafe roles are `unverified`, equal content can
coexist with different provenance. Stable keys without PK use full row identity.
Duplicate records are accounted for via multiplicity.

The source-attestation operation hashes enabled project source files, comparing
their bytes to project SHA-256 and recorded `source_restore_status_json`.
Only aggregate match/change/missing/unsafe counts are returned. This is a real
private-content READ, not a content-free metadata inspection.

Memory generation, source union, restore run and optional DB UUID are compared
as lineage CLAIMS, not independently verified ancestry. Missing or conflicting
claims remain `unverified`/`different`/`conflict`. No parent SHA chain
or runtime process identity is certified.

The operation is bounded (1M semantic rows/database, 8 GiB/database,
8 GiB/source group, snapshot deadline 90s, free-space preflight).
Exceeding a limit fails closed; it NEVER returns partial equality.
Temporary snapshot root must not be inside SYSTEM or selected target.
No model/API calls, daemon activation, publish, restore, automatic L2/L3,
or persistent private report.

## Test/acceptance

Run synthetic fixtures for equal, added, removed, modified, duplicate records,
schema mismatch, lineage conflict, WAL replay, missing/legacy/symlink roles,
source drift, resource limits, private output redaction and snapshot cleanup.
Then full deterministic pytest, Windows targeted, Pyright, compileall,
doctor/package-smoke, canonical Test Studio sync and release metadata.
No operational MEMORY validation or ChatGPT accepted-turn claim.

Official references:
- https://www.sqlite.org/backup.html
- https://www.sqlite.org/wal.html
- https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup

## Hardening checkpoint 16.3.25.5.115.21.3.1

Snapshot-root containment also covers the host-selected MEMORY directory and the configured project source directory; backups can no longer be placed inside private MEMORY via an explicit temp_root. Source SHA-256 attestation checks size/mtime/inode before and after streaming to avoid recording a passing digest across source mutation. New native-unified synthetic and WAL snapshot tests independently exercise the real resolver and online-backup integration; they are not a real private MEMORY activation or accepted-turn test.

## WAL snapshot normalization 16.3.25.5.115.21.3.2

Observed using real local SQLite: Online Backup API may produce a standalone copied database with WAL header bytes 2/2 and no persistent -wal/-shm sidecars. After the backup completes and the source connection closes, the comparator switches *only the temporary destination* to journal_mode=DELETE, then runs the strict native SQLite inspection. This conversion does not checkpoint or write the source. See https://www.sqlite.org/backup.html and https://www.sqlite.org/wal.html. Native WAL regression added in v115.21.3.1 must pass on Windows/Linux.
