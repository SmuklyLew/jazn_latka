# Jaźń v16.1.2 — private-memory acceptance benchmark

Version: `16.1.2-private-memory-acceptance-benchmark`

## Scope and truth boundary

This stage implements the anonymized, fail-closed acceptance harness required by
GitHub Issue #59. It validates a locally supplied native unified SQLite database,
private recall cases and source manifest. It never copies private inputs into the
repository, never activates the tested database, never authorizes L3 promotion and
never treats synthetic fixtures as proof of private-memory quality.

The private execution report contains only hashes, counts, timings and pass/fail
evidence. Queries, expected phrases, recalled content, source names and source paths
are not persisted in that report.

## Runtime and retrieval hardening

- Native unified-source discovery is cached per gateway instance and can be
  explicitly invalidated. This removes repeated full integrity probes from a single
  benchmark while preserving fresh discovery across gateway instances and restarts.
- Retrieval uses bounded focus and expansion passes, FTS exact/prefix fallbacks,
  global relevance ordering and result deduplication. The legacy five-database layout
  remains read-only compatibility only.
- Conversation graph traversal is iterative and cycle-safe. A real private archive
  exposed recursion failure on a graph deeper than Python's call-stack limit; the
  regression now covers 2,000 nodes and a back edge.

## Private acceptance result

The available private unified database passed full SQLite integrity, foreign-key and
FTS parity checks. It contained 1,043 conversations, 144,105 nodes, 70,018 searchable
archive documents and 533 searchable journal entries. No duplicate source hashes,
orphaned conversation/import references, experiences, durable memory records or
automatic promotion decisions were found.

Recall acceptance did **not** pass:

- 6 of 15 cases passed at their configured limit;
- 6 of 13 cases whose expected evidence was actually present passed;
- recall@20 was `0.266667`;
- the explicitly labelled wrong-conversation proxy was `0.719626`;
- temporal ordering accuracy was `1.0` and no superseded rows were returned;
- the no-evidence abstention probe returned zero hits;
- the automated two-turn referential follow-up did not pass;
- 44 of 47 expected evidence terms were present in the database.

The seven attested source ZIPs all existed, but zero of their exact SHA-256 values
were registered in the selected database. Source provenance therefore fails closed.
The harness does not infer equivalence from filenames, dates, sizes or content overlap.

## Review-only L2/L3 snapshot

A separate private SQLite snapshot passed full validation. Candidate generation found
63 review candidates (52 from conversations and 11 from journal entries). It created
zero experiences, zero L2 records and zero L3 records. No automatic promotion was
performed or authorized. Manual naturalness and candidate review remain required.

## Restart continuity

The current code was copied into a manifest-verified isolated system staging. A
canonical host-level memory-source registry selected exactly one native unified
database. Two daemon starts on the same isolated loopback endpoint both reached
`active_trusted`; the first daemon was stopped, the second had a different PID, and
the private recall fingerprint was identical before and after restart. The active
system daemon and active memory were not modified.

## Issue #59 decision

Issue #59 remains open. Private data were available, so this is not an
`unavailable_private_data` result. The acceptance blocker is measured retrieval
quality plus exact source-provenance mismatch. Later graph-aware retrieval work may
be evaluated in shadow/A-B mode against this unchanged benchmark, but no result from
this stage permits activation or automatic L2/L3 promotion.

## Verification

- focused private-acceptance and deep/cyclic graph regressions: `5 passed`;
- memory/export-selected suite: `103 passed, 2 skipped`;
- Pyright 1.1.411: `0 errors, 0 warnings`;
- semantic route audit: `132/132`, `ok=true`;
- cognitive architecture audit: all checks passed;
- current-line archive audit: `old_refs=0`, `archive_issues=0`;
- system package smoke: `14` required checks passed, `ok=true`; the only optional
  failure is the intentionally stale source-checkout manifest in a dirty development
  tree, while the ephemeral staging manifest and provenance both verify.

Protected-path closure found no repository changes under `memory/` or
`workspace_runtime/`, and no SQLite, WAL/SHM, ZIP, secret, raw private export or
generated package artifact is part of this release change.
