# SQLite existing-WAL write gate — PR #454

Status: partial WAL hardening / RELEASE_NOT_ACCEPTED.

The verified project and base Python3.14.4 both load SQLite3.50.4. JSS runtime,
workers, TPA and MCP currently select the project interpreter. No library or
package was installed or replaced. The interpreter observations are retained
outside Git in the task report.

SQLite documents the WAL-reset race for concurrent writes/checkpoints on affected
builds, with fixes in3.51.3 and backports3.50.7/3.44.6:
https://sqlite.org/wal.html#wal_reset_bug . A passing stress test is not proof
that the loaded SQLite library contains that fix.

The existing central policy selects DELETE on affected builds and WAL on fixed
builds. This patch additionally rejects an existing WAL-format database before
opening it writable on an affected build. It reads only the SQLite header and
leaves the database and WAL/SHM bytes unchanged; it does not silently checkpoint
or convert an existing database. A post-open mode check also refuses unexpected
WAL instead of converting it. Genuine filesystem errors remain errors.

ChatExportArchiveStore, the rebuild Store and Test00 source mirror now use the
central connector. This prevents the archive component from changing a shared
unified rebuild database back to WAL. Existing timeout, autocommit, cache and
synchronous contracts are retained. Test00 checkpoints only an actually enabled
WAL mode, which the central policy enables only on fixed SQLite builds.

Diagnostics explicitly scope this mitigation to central writable connections
and set all_sqlite_writers_verified=false. The process/file lock covers only
cooperating guarded operations; it is not presented as universal SQLite coverage.

Synthetic-only tests cover refusal before sqlite3.connect, unchanged file bytes,
fixed-library policy, rollback writes, permission errors, three concurrent worker
processes,150 durable rows, integrity_check, foreign_key_check and shared archive/
rebuild journal policy. Existing archive/rebuild regression assertions remain.
No private database was opened, checkpointed or migrated by the tests.

Remaining WAL gate: audit/direct-writer integration in mcp/task_resume.py and
memory/html_memory_ingest.py, including explicit checkpoint callers in restore
and legacy recovery. Do not close the PR's global WAL checklist from this patch
alone. Voice-perspective validation, final new-SHA Windows acceptance and the
separate synthetic persistent-MEMORY E2E also remain mandatory.

Evidence directory: D:\.AI\codex_tasks\pr454-finalization-20261104.
wal.txt/xml: initial central gate14 PASS. wal-regression.txt/xml preserves the
intermediate41 PASS/24 FAIL caused by the archive's conflicting WAL policy.
wal-final.txt/xml and wal-final-evidence contain the corrected regression result.
pyright.txt records the changed-file static check. Metadata must still be
canonically synchronized and checked for the final source commit.
