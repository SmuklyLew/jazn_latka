# Jaźń P1 — Active Memory Evidence & Readiness (v16.3.25.5.115.21.4)

This task completes WIP checkpoint `8acea9c5`, stacked on PR #347.
No private MEMORY data are included in the code or tests. No automatic
activation, migration, publish, memory repair, daemon restart, or MCP claim.

## Scope and authoritative evidence

- The actual loopback daemon serves authenticated
  `GET /active-memory-evidence?nonce=<32 lowercase hex>`, using its
  already established capability token. Nonce, HMAC proof, runtime instance
  and PID are checked independently at the operator.
- Operator transport rejects redirects, oversized response bodies and wrong
  media types. Process command, fingerprint, root, manifest/version, heartbeat,
  configured MEMORY root and native database schema are checked separately.
- This is **configured DB observation**, not proof of a real successful
  recall, continuity or an accepted ChatGPT visible turn.
- Read-only Memory Studio displays `assess_active_memory_readiness`,
  containing only status codes, never raw private paths, secrets or metadata.
- Independently operator-pinned *frozen* SQLite artifacts may establish one
  exact SHA-256 binding and optionally one parent edge. No metadata
  self-certification, no claim of historical reconstruction correctness.
- WIP type-tagged SQLite content hashing remains part of the record-level
  diff. Full cross-database observation is not atomic.

`runtime_ready` refers only to the verified daemon+configured database
observation. `memory_recall_ready` and `memory_continuity_ready` stay null.
`activation_preflight_passed` and `activation_authorized` are **always false**
in this stage; their future owner requires operator approval and independent
recall/continuity/turn evidence.

## Acceptance

Synthetic checks: authenticated endpoint, unauthorized GET, malformed nonce,
signed response, redaction, absent daemon, source pins, parent missing,
hash mismatch, symlink, BLOB/text/integer type separation.
Regression: native unified SQLite, WAL backup, prior MCP and runtime tests.

Required: local targeted pytest, full Ubuntu/Windows CI, Pyright, compileall
excluding immutable historical test snapshots, doctor, package smoke and
canonical release metadata synchronization.

Do not edit `PACKAGE_INTEGRITY_MANIFEST.json` or `SOURCE_PROVENANCE.json`
manually; their GitHub workflow owns final materialization.

References: https://www.sqlite.org/backup.html and
https://www.sqlite.org/wal.html .
