# Living memory recall runtime update

## Scope

This update repairs the path between the rebuilt five-database memory architecture and the conversational runtime. It does not migrate, rewrite, promote, or delete autobiographical records. The new gateway is read-only.

The target memory layout remains:

1. `memory_jazn.sqlite3`
2. `experience.sqlite3`
3. `journal.sqlite3`
4. `archive_chats.sqlite3`
5. `import_catalog.sqlite3` for operational state only, never autobiographical recall

## Observed failure

The runtime correctly recognized questions about Łatka's memories, but its recall path continued to read the legacy runtime-write database, legacy conversation archive, and raw files. The rebuilt five databases were created by the recovery pipeline but were not queried by the live conversational path. As a result, a turn could end with `topic_aligned_no_source` even when the rebuilt archive contained relevant evidence.

Two conversational forms exposed the gap especially clearly:

- chronological recall: `Co pamiętasz jako pierwsze?`
- referential continuation: `Poszukaj tego wspomnienia`

A separate operational problem caused long research and repository-update turns to lose their second-phase host contract after the previous 15-minute lease.

## Changes

### Read-only living-memory gateway

`LivingMemoryGateway` discovers memory sources from:

- `memory/sqlite` below the active runtime root;
- the path-separated `JAZN_MEMORY_SOURCE_ROOTS` environment variable;
- enabled, read-only entries in `workspace_runtime/memory_source_registry.json`.

SQLite databases are opened with `mode=ro`, `PRAGMA query_only=ON`, and a bounded busy timeout. The gateway exposes no write, migration, promotion, or invalidation operation.

Recall follows the architectural order:

1. active L1/L2/L3 records in `memory_jazn.sqlite3`;
2. structured experiences in `experience.sqlite3`;
3. journal entries in `journal.sqlite3`;
4. exact source evidence reconstructed from `archive_chats.sqlite3`.

`import_catalog.sqlite3` is explicitly excluded.

Each hit carries its source database, record locator, timestamp, truth status, confidence, importance, relevance, and grounding label. A journal entry or source message remains evidence; it is not silently promoted to L3 and is not described as a biological feeling.

### Search planning

The planner now distinguishes:

- `semantic_query`;
- `chronological_earliest`;
- `chronological_latest`;
- `referential_followup`.

A follow-up such as `Poszukaj tego wspomnienia` may project the immediately preceding recall query instead of searching only generic pronouns. Chronological requests are no longer treated as ordinary keyword searches.

### Runtime integration and diagnostics

The live engine executes the living-memory pass before legacy fallback sources. Returned evidence is included in the memory context, recall presentation, source-origin analysis, and grounding contract. Raw-chat fallback is not invoked after a successful five-database hit.

When no trustworthy hit is available, the diagnostic now reports:

- selected search mode;
- five-database source state;
- number of ready sources;
- first source error, if any;
- a concrete next action.

The system still retains the valid result `no confirmation found`; absence of evidence is not replaced with a generic autobiographical claim.

### Host continuation lease

The pending second-phase host contract now uses:

- 1 hour for ordinary host-visible generation;
- 4 hours for research, architecture audit, memory audit, runtime repair, diagnostic repair, and system-update work.

The continuation remains one-time, HMAC-bound, linked to the same turn/trace/contract hash, and protected against replay. Only the expiry window changes.

## Engineering basis

- SQLite FTS5 documents that lower `bm25()` values are better matches and should be ordered ascending. The journal and archive paths use this convention: <https://www.sqlite.org/fts5.html>
- SQLite recommends the Online Backup API or `VACUUM INTO` for consistent snapshots of live databases rather than ordinary file copying during WAL activity: <https://www.sqlite.org/backup.html>
- LongMemEval evaluates information extraction, multi-session reasoning, knowledge updates, temporal reasoning, and abstention. Its reported design improvements include time-aware query expansion and decomposed retrieval: <https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html>
- LongMemEval-V2 frames memory as compact evidence gathering over historical state, events, workflows, and failure modes rather than unbounded context injection: <https://arxiv.org/abs/2605.12493>

These sources support guarded retrieval and evaluation criteria; none provides an error-free universal memory function. The implementation therefore keeps provenance, explicit abstention, bounded result sets, and regression tests.

## Validation

Completed locally against the current source line:

- Python compilation: passed;
- 70 tests covering the living gateway, rebuilt databases, Test 04 contracts, source archive, two-phase host protocol, and runtime memory status: passed;
- 32 additional tests covering routing boundaries, host bridge regressions, restart continuity, full-turn behavior, diagnostics, and non-blocking timeout audit: passed;
- read-only smoke test against the real Test 03 database set:
  - chronological query returned source-bearing hits;
  - referential follow-up preserved the chronological mode;
  - `Katedra` query returned exact archive evidence;
  - no SQLite source errors were reported;
- runtime doctor: passed before modifying the isolated work copy.

A full repository suite was attempted in an isolated synthetic checkout, but did not finish within the tool limit. The failures seen before timeout were repository/provenance checks that require canonical Git metadata. Release metadata and package-integrity manifests are intentionally not edited by this patch and must be regenerated by the repository's canonical release workflow.

## Known boundary

The rebuilt Test 03 journal contains some early records marked `truth_status=inferred`, including timestamps earlier than the earliest confirmed conversation in the source archive. The gateway exposes those fields instead of claiming they are definitive first-life events. Test 04/private validation must determine whether such records are accepted, corrected, superseded, or rejected before any L3 promotion.
