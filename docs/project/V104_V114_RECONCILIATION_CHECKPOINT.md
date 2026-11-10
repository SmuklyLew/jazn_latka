# V104/V114 reconciliation — incremental implementation checkpoint

Release acceptance remains **NOT_RUN / RELEASE_NOT_ACCEPTED**. This is an
incremental checkpoint, not completion of the requested reconciliation.

## Source identity

- Working branch: `audit/v114-v104-gap-reconciliation-tpa-20261109`.
- Starting HEAD: `5e5888b35dad5531e74e5ba8e8eb33d34b93f962` (clean).
- V104: `b98ff9599e2f7d6f75d4528d3baa0e935993735c`.
- V114: `6f744dd74bb641cebe1b861294622a62ae49599d`.
- Verified common ancestor: `5adef1d6e3c911f9ccd0bf884b32c0364c866481`.
- GitHub branch HEAD matched the starting HEAD; Actions returned no runs for it.
- Account usage: `usage_unknown`.

## Stage 1: MCP transport and durable task database (.115)

| Difference | Decision | Evidence / rationale |
|---|---|---|
| `mcp/http_tasks_bridge.py` buffered receive | PORT | A consumed body is not a disconnect. Replay body once, then await the real receive channel. Preserve SDK response lifetime and actual disconnect propagation. |
| `mcp/task_resume.py` connection policy | PORT | Replace private unconditional WAL bootstrap with `connect_runtime_writable`; preserve task ownership, request IDs, receipt ledger and BEGIN IMMEDIATE transactions. |
| `db/runtime_sqlite.py` V104 policy | SUPERSEDED | Current V114 file already equals V104, including fixed-library journal selection, existing-WAL refusal and extended Windows URI handling. No reverse port. |
| Two V104 MCP regression files | PORT | Added byte-for-byte from the V104 SHA above: `test_mcp_http_body_replay_lifetime.py`, `test_mcp_task_sqlite_journal_policy.py`. They were absent in starting HEAD; no existing active test was modified. |

Authoritative specifications checked on 2026-11-09:
[ASGI HTTP](https://asgi.readthedocs.io/en/stable/specs/www.html),
[SQLite WAL](https://www.sqlite.org/wal.html).

Actual native executor: Python 3.14.4, SQLite 3.50.4, pytest 9.0.3, MCP 2.2.0.
Synthetic databases only. The default sandbox blocked asyncio socketpair;
the default native pytest temp directory also denied access. The successful
run used an explicit new basetemp outside the sandbox. No daemon was started.

Validation: **45 passed, 1 skipped**. Selected files:

- `test_mcp_http_body_replay_lifetime.py`
- `test_mcp_task_sqlite_journal_policy.py`
- `test_mcp_http_tasks_bridge.py`
- `test_mcp_http_tasks_nonblocking_dispatch.py` — collection SKIPPED: missing httpx
- `test_mcp_task_registry.py`
- `test_mcp_task_lifecycle_bounds.py`
- `test_mcp_task_principal_isolation.py`
- `test_runtime_sqlite_hardening.py`
- `test_runtime_sqlite_existing_wal_gate.py`

JUnit: `C:/Users/smukl/AppData/Local/Temp/jazn-v115-p0-regression.xml`.
Canonical TXT/JSON evidence: `C:/Users/smukl/AppData/Local/Temp/jazn-v114-reconcile-evidence/`.
Reports bind the dirty source tree; they are not exact-final-SHA CI acceptance.
Targeted compilation and `git diff --check` passed.
Local Pyright is unavailable; remote type gate remains required.

## Next required work

1. Finish per-hunk triage of all remaining V104 differences. Initial diff confirms
   remaining candidates in HTML ingest, unified memory connections, finalization
   repair guidance, Ollama endpoint probes/live TPA, supervisor status, NLP time
   routing, pinned path helper, dependency CLI layout and version audit.
2. Preserve newer V114 daemon/startup changes. `windows_supervisor.py` and
   `runtime_supervisor.py` already equal V104; their end-to-end callers still
   require review and tests.
3. Verify all 22 canonical TPA mappings, procedures and evidence without creating
   a second runner. Operator gates remain NOT_RUN. Local PySide6 is unavailable.
4. Complete version/metadata checks and exact-final-SHA required CI, then actual
   Windows TPA acceptance before the final PR. Do not merge master.

No private MEMORY, active marker, production daemon or master was modified.
