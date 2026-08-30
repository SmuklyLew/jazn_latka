# Jaźń v15.4.0.1 — Runtime Resilience Hardening

**Target:** `v15.4.0.1-runtime-resilience-hardening`
**Baseline:** `v15.4.0.0-cognitive-architecture`
**Scope:** daemon turn liveness, deadline/cancellation propagation, memory recall cancellation, mixed tool+execution routing, late-result safety, regression coverage.

## Incident that triggered the hardening

A real ChatGPT-hosted deep-memory turn remained in daemon state `running` after its configured execution deadline. The host could only keep returning `poll_runtime`, while the job never transitioned to a terminal timeout state. This violated the existing runtime contract, whose timeout layer was intended to return a controlled timeout rather than hang.

## Root causes

1. The daemon marked a job `running` before session acquisition, but the hard timeout lived primarily inside `RuntimeSessionWorker.process_user_text()`. A stall outside that inner watchdog could therefore leave the daemon job non-terminal.
2. The daemon used one queue-consumer thread. A blocked orchestration path could poison that consumer even when the daemon process itself remained alive.
3. `DEFAULT_DAEMON_CHAT_TIMEOUT_SECONDS = 180` and the CLI `--daemon-chat-timeout` already existed, but the server constructor fell back to the generic runtime-turn budget (45 seconds), and `main.py` did not propagate the daemon CLI value into daemon start/run.
4. Deep memory recall used a comparatively short default hard deadline and not every legacy/archive SQLite read path received the shared turn cancellation signal.
5. A leading `@Wyszukiwanie w sieci` marker could take primary routing away from an explicit system-update execution request. Conversely, negated write instructions required stronger protection against execution routes.

## Implemented corrections

### Daemon liveness and watchdog

- Added an independent daemon chat watchdog that observes the shared `TurnExecutionContext` deadline.
- An overdue non-terminal job is atomically terminalized as `execution_timeout`, its done event is set, cancellation is recorded and a late result cannot overwrite the terminal state.
- When a running queue consumer is poisoned, the watchdog advances the worker generation and starts a fresh consumer; the old thread exits after it eventually returns.
- A timed-out active `RuntimeSessionWorker` is retired and cannot be reused.
- Watchdog state/generation is exposed in daemon job diagnostics.

### Deadline separation

- Generic one-shot/runtime-session default remains 45 seconds.
- Persistent daemon hard execution budget now uses the already intended daemon-specific default: 180 seconds.
- Deep-recall hard budget is 600 seconds.
- `--daemon-chat-timeout` is propagated through `main.py`, daemon start and child command construction.
- Client wait/poll behavior remains separate from execution failure; a short client wait still produces polling rather than killing healthy work.

### Cancellation propagation into memory

- Conversation archive FTS accepts a shared continuation callback, checks it before work and installs a SQLite progress handler during queries.
- Legacy message and episodic-memory queries now have both a pre-query cancellation check and SQLite progress-handler cancellation.
- Engine and layered-memory paths propagate `TurnExecutionContext.can_continue`.
- SQLite interruption is fail-soft for cancelled recall: cancellation produces an empty/cancelled recall result rather than an unrelated runtime exception.
- Late timeout audit persistence is asynchronous so audit I/O cannot hold a retired worker open.

### Semantic routing

- Explicit authorized system execution outranks web/tool markers; research remains a secondary capability requirement.
- Negated or diagnostic-only write language cannot become `system_update_execution_request`.
- Both semantic-route corpus and v15.4 cognitive dialogue benchmark now contain mixed web+execution and negated-write regressions.

## External engineering basis

The implementation follows primary-source behavior documented by Python, SQLite and gRPC:

- Python futures cannot cancel already-running work, so logical terminalization and late-result suppression must not depend on killing a Python thread.
- SQLite exposes `sqlite3_interrupt()` and progress handlers specifically for cancelling expensive database work.
- gRPC deadline/cancellation guidance separates bounded waiting from downstream cancellation and recommends deadline propagation rather than orphan work.

See `docs/reports/JAZN_V15_4_0_0_RESEARCH_SOURCES.md` for exact source links and design consequences.

## Validation performed in the development checkout

- package/system source baseline ZIP integrity: verified before development;
- targeted mixed routing regressions: green;
- semantic route audit: 132/132 scenarios green;
- cognitive architecture audit: 12/12 dialogue regressions green;
- daemon/timeout/atomicity targeted regressions: green;
- cross-layer routing/runtime/memory selection: 142/142 green;
- compileall: green;
- code-health/type-boundary regressions: green;
- full deterministic non-live suite: **665 passed, 3 skipped, 0 failed**;
- real memory package SHA-256: verified;
- real conversation archive SQLite quick-check: `ok`;
- real runtime-memory SQLite quick-check: `ok`;
- real archive FTS queries for representative terms returned in roughly 0.03–0.05 s in the current test environment;
- pre-cancelled real archive query returned `cancelled` with zero hits immediately.

The supplied memory package intentionally predates the final L0/L1/L2/L3 layout and therefore cannot prove full new-tier readiness. The hardening does not reinterpret that absence as a successful L0–L3 state.

## Release gate

This report does not authorize merge by itself. Before `master` update the source branch must pass canonical metadata synchronization and GitHub release-hardening (Ubuntu + Windows, including Pyright and deterministic tests) on the exact synchronized branch head.
