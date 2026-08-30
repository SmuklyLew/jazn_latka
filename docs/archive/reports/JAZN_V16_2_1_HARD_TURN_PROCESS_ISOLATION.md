# Jaźń v16.2.1 — hard turn process isolation

Version: `16.2.1-hard-turn-process-isolation`

## Scope and truth boundary

Production daemon sessions now execute runtime turns inside replaceable child
processes created with the cross-platform `spawn` start method. The HTTP daemon,
job queue, watchdog, recovery metadata and host-finalization lifecycle remain in the
parent process. This is operational fault containment; it is not a claim about
biological life or phenomenal consciousness.

Compatibility callers and tests that inject a non-production session factory remain
on the existing thread worker unless they explicitly request process isolation. The
daemon reports `hard_worker_process_isolation=true` only when the process worker is
the selected execution mode. It continues to report
`running_thread_hard_cancel_supported=false` truthfully.

## Deadline and replacement lifecycle

Each process worker owns its runtime session and thread-bound SQLite resources. The
parent sends only a bounded request envelope. A fresh child-local
`TurnExecutionContext` carries the same request, turn and session identifiers; locks
and staged write callbacks never cross the process boundary.

At the hard deadline the parent:

1. marks the parent turn context cancelled;
2. signals cooperative cancellation to the child;
3. waits a configured bounded grace period;
4. terminates the child if it is still running;
5. kills it if termination does not complete;
6. permanently retires that worker so the next turn receives a fresh process.

Late results are never accepted. Child crash, invalid response and serialization
failure are structured process errors and retire the session without automatic
replay. Timeout diagnostics include the child PID, parent PID, grace period,
termination outcome and timeout owner. The parent daemon PID remains unchanged.

## Atomic persistence boundary

Semantic writes continue to be staged in the turn-local context and are rejected
after cancellation or deadline expiry. The child deadline reserves a bounded
finalization margin inside the parent's hard deadline. The killed-precommit
regression stages a real write callback, blocks forever and verifies that the target
does not exist after termination. SQLite interruption is process-scoped, so an open
SQLite transaction is rolled back by SQLite when the child exits.

This guarantee is deliberately stated narrowly: a killed or timed-out turn cannot
turn an uncommitted staged write into an accepted result. Existing canonical commit
gates and compensating/recovery metadata remain responsible for failures occurring
inside an already-authorized multi-write commit.

## Durable host finalization

Phase-1 host-generation results do not commit final-answer state. Their pending
request contract is persisted separately, while the daemon job stores only recovery
metadata in the parent. Replacing the phase-1 worker therefore cannot delete or
complete that continuation.

The regression creates a real pending host request in an isolated runtime root,
retires its worker, closes the daemon and constructs a new daemon on the same root.
The recovered job remains `awaiting_host_finalization` with the same turn ID and
contract hash. No user message is replayed.

## Windows fault-injection verification

The process suite runs with Python 3.12 on Windows and covers:

- an infinite Python loop;
- a long recursive SQLite query;
- a simulated model call that exceeds its deadline;
- cooperative cancellation followed by terminate/kill telemetry;
- unchanged parent PID and a distinct child PID;
- a new child PID and successful result on the next turn;
- absence of the staged pre-commit sentinel after the killed turn;
- truthful process/thread capability status;
- pending host continuation across worker replacement and daemon restart.

## Additional regressions repaired

The first full-suite run exposed two code-health debts from earlier convergence
stages and one stale version assertion. Cognitive-control wiring was extracted from
the known `JaznEngine.process_turn` hotspot, the daemon readiness probe now catches
only expected transport/decoding/value failures, and the release identity contract
now names 16.2.1. No analyzer suppression or budget increase was used.

## Verification

- hard-process fault-injection suite: `7 passed`;
- daemon, timeout, atomicity, persistence and two-phase host suite: `75 passed`;
- full repository suite after repairs: `859 passed, 6 skipped`;
- full Pyright 1.1.411 analysis: `0 errors, 0 warnings`;
- semantic route audit: `132/132`, `ok=true`;
- cognitive architecture audit: all `24` checks true and dialogue regressions
  `12/12` true;
- code-health budgets: `2 passed`;
- current-version literal violations: `0`; generated release metadata remains
  intentionally stale until the single final metadata synchronization after stage G;
- diff whitespace check: clean.

Protected-path closure must find no repository changes under `memory/` or
`workspace_runtime/`, and no SQLite, WAL/SHM, ZIP, secret, raw private export or
generated package artifact may be included in the stage commit.
