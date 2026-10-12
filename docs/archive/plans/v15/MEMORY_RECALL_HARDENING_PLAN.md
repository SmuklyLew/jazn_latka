# Memory recall hardening plan

**Scope:** bounded runtime turns, cancellable SQLite recall, FTS-first retrieval, memory-query planning and per-stage telemetry.

**Status:** phase 1 implemented on the hardening branch; phases 2–4 remain gated follow-up work.

## 1. Failure that motivated the work

A deep autobiographical recall request exhausted the fixed 45-second runtime-turn budget. Inspection showed several interacting causes rather than one isolated slow query:

- every turn shared the same 45-second hard deadline;
- a book-history request containing both "pierwsza wersja" and "wspomnienia" could be misrouted as chronological-earliest recall;
- the planner could emit a wide set of low-value lexical terms;
- indexed archive retrieval could be followed by redundant legacy `%LIKE%` scans;
- cancellation at the turn boundary did not propagate into SQLite queries;
- memory telemetry was too coarse to identify which recall layer consumed the budget.

The repair must improve retrieval quality and bounded cancellation, not merely raise the timeout.

## 2. Research basis

Primary technical sources used for this plan:

- Python `sqlite3.Connection.set_progress_handler()` can terminate a running SQL statement when its callback returns non-zero, and `Connection.interrupt()` can abort queries from another thread: https://docs.python.org/3.12/library/sqlite3.html
- SQLite FTS5 provides indexed full-text `MATCH`, prefix queries/indexes, BM25/rank ordering, snippets and index maintenance operations: https://www.sqlite.org/fts5.html
- Python futures cannot cancel a callable that is already running, so cooperative cancellation must reach the work itself instead of only the wrapper/future: https://docs.python.org/3/library/concurrent.futures.html
- LongMemEval separates long-term memory into indexing, retrieval and reading, and reports gains from session decomposition, fact-augmented keys and time-aware query expansion: https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html
- LongMemEval-V2 frames memory as gathering compact evidence under an accuracy/latency trade-off rather than rereading the whole history: https://arxiv.org/abs/2605.12493

These sources support the architectural direction. They do not by themselves prove that any specific Jaźń timeout was caused by SQLite; that conclusion must come from Jaźń telemetry and tests.

## 3. Phase 1 — runtime and recall hardening

### 3.1 Adaptive turn budget

Keep the ordinary-dialogue deadline unchanged. Give only broad/deep autobiographical or archive-recall turns a larger hard deadline through a conservative pre-routing profile.

Acceptance criteria:

- ordinary dialogue retains the existing default budget;
- deep recall receives the configured extended budget;
- the selected timeout profile and effective seconds are visible in technical telemetry;
- timeout remains a hard bound, not an infinite wait.

### 3.2 Propagate cancellation into SQLite

Read-only living-memory/archive connections receive the turn cancellation/deadline callback through SQLite's progress handler.

Acceptance criteria:

- an expired/cancelled turn aborts a long SQLite statement;
- the database remains read-only;
- cancellation is reported as a controlled recall issue rather than hidden;
- no memory SQLite file is modified by this patch.

### 3.3 FTS-first retrieval

Prefer the indexed archive path. When archive FTS has already produced source-backed candidates, skip the redundant legacy-message `%LIKE%` pass for that turn. Keep the legacy scan only as a fallback when indexed archive evidence is absent.

Acceptance criteria:

- archive evidence retains provenance and truth status;
- legacy fallback remains available;
- a verified archive FTS hit prevents the redundant legacy-message scan;
- selected results remain bounded.

### 3.4 Planner repair

Disambiguate a document-history modifier such as "pierwsza wersja książki" from an actual request for "pierwsze wspomnienie". Add a dedicated topic for the historical book titles and reduce generic/noise terms.

Acceptance criteria:

- a request about the first book version routes semantically, not chronologically;
- a genuine first-memory request still routes to chronological-earliest recall;
- historical book titles are retained as high-value search terms;
- the total query expansion is bounded.

### 3.5 Per-stage telemetry

Split memory retrieval into independently timed stages:

- search plan;
- living-memory recall;
- legacy fallback recall;
- canonical source-file scan;
- conversation archive recall;
- raw-chat fallback.

Acceptance criteria:

- a future timeout can identify the expensive layer;
- FTS-first skip is emitted as a technical retrieval-strategy event;
- cancellation status propagates to stage telemetry.

## 4. Phase 2 — wake-state stability

Do not fold this into the timeout patch without dedicated fixtures. The current wake-state can invalidate on relevant-row revision changes even when the content-level fingerprint reports no relevant content change.

Planned work:

1. distinguish logical-content changes from bookkeeping/revision-only changes;
2. persist both content and revision fingerprints;
3. rebuild wake-state only when a truth-relevant semantic change requires it;
4. add fixtures for WAL/checkpoint-only, revision-only and real-content changes;
5. expose the exact invalidation reason in status.

## 5. Phase 3 — curated long-term memory without automatic L3

The architecture explicitly forbids blind automatic promotion to L3. Keep that boundary.

Planned work:

1. create a review queue from source-backed repeated/high-importance candidates;
2. group evidence by semantic identity instead of duplicating memories;
3. require conflict checks and explicit promotion decisions;
4. preserve source links and revision history;
5. use L3 as the first compact recall layer, then descend to archive evidence only when needed.

## 6. Phase 4 — private recall benchmark

Build a project-specific evaluation set from manually reviewed conversations without publishing private content.

Measure at minimum:

- evidence recall@k;
- wrong-conversation rate;
- temporal ordering accuracy;
- superseded-fact handling;
- abstention when evidence is absent;
- p50/p95 recall latency per layer;
- total turn latency;
- number of source rows/tokens read;
- restart reproducibility.

Include cases for:

- book-title/history reconstruction;
- self vs user memory boundaries;
- emotional/philosophical conversations;
- multi-session continuity;
- conflicting or updated facts;
- source-only evidence that must not become L3 automatically.

## 7. Non-goals of phase 1

- no version bump;
- no automatic L3 promotion;
- no edits to `memory/`, `workspace_runtime/`, SQLite/WAL/SHM, active markers or runtime logs;
- no replacement of source-backed recall with model-only inference;
- no promise that every deep recall completes within the extended budget; it must still fail closed when the hard deadline is reached.

## 8. Rollout order

1. merge phase-1 hardening only after full non-live test suite, doctor and package-smoke pass;
2. use new stage telemetry on real deep-recall requests;
3. tune the deep-recall budget from measured p95 rather than guesses;
4. implement wake-state fingerprint fixes as a separate change;
5. build the private benchmark before promoting substantial memory to L3;
6. only then tune retrieval weights/FTS prefix indexes from measured benchmark failures.
