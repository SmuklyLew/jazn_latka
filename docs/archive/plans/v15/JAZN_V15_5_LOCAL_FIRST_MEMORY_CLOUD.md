# Jaźń v15.5 candidate — local-first memory, encrypted cloud durability, sandbox transport

## Status

This document defines the implementation contract for branch `upgrade/local-first-memory-cloud-v155`.
It is an engineering plan and truth boundary, not a claim that a public cloud deployment is already configured.

## Non-negotiable architecture boundary

Jaźń has three different planes and they must remain separable:

1. **Local runtime and memory plane** — normal desktop operation. Python modules and SQLite files are used directly from the local runtime root. No ZIP file and no cloud service is required for startup, turns, local memory commits, recall, wake-state, or local continuity.
2. **Cloud durability and synchronization plane** — optional encrypted replication and verified restore. It receives client-side encrypted event envelopes and immutable encrypted snapshot objects behind an authenticated API. The cloud is not a network filesystem for SQLite.
3. **ChatGPT sandbox transport plane** — ZIP is only a packaging adapter for moving a verified system/memory snapshot into the ChatGPT sandbox. Binary `.001/.002/...` split parts are transport fragments of a completed ZIP, never SQLite shards and never a local runtime format.

Normal local code must remain usable if the packaging modules are removed from the environment and if the network is completely unavailable.

## Why the network boundary is above SQLite

SQLite documents that network filesystem locking/synchronization semantics can make direct database use over a network unreliable, and WAL requires processes to share the WAL index on the same host. The Jaźń cloud boundary is therefore an API/event/snapshot boundary, not NFS/SMB/WebDAV/S3-mounted SQLite.

Source: <https://www.sqlite.org/useovernet.html>

Consistent SQLite snapshots use the SQLite Online Backup API (`sqlite3.Connection.backup()` in Python), not raw copying of an active WAL database.

Source: <https://www.sqlite.org/backup.html>

## Local transaction is the truth boundary

`MemoryTierStore` remains the canonical local transactional store for L1/L2/L3 records, evidence, promotion ledger, outbox and checkpoints. A cloud request is never made inside the local memory transaction.

The write sequence is:

1. write canonical memory/evidence/promotion locally;
2. write `memory_outbox` intent in the same SQLite transaction;
3. commit locally;
4. background or explicit sync claims the outbox record;
5. serialize a versioned sync event;
6. encrypt it on the client;
7. push the encrypted envelope;
8. verify a receipt bound to event identity and ciphertext hash;
9. only then mark the outbox row processed.

If the response is lost after the server commit, retry reuses the exact persisted encrypted envelope. The server must return the same `remote_seq` for the same immutable event identity. A different ciphertext under the same event/idempotency identity is a conflict, never an overwrite.

## Synchronization modes

- `off` — default. No controller thread, no cloud credential requirement, no network activity.
- `backup` — encrypted local events are pushed to the remote durable replica. No remote event is materialized into local memory.
- `push_pull` — encrypted push plus ordered pull. A single-writer lease is enabled by default for this mode.

Cloud sync failure is a durability degradation only. It cannot make `live_runtime_ready`, local memory or ordinary dialogue false.

## Writer lease

The first production multi-device contract is deliberately single-writer. `push_pull` requires a high-entropy writer lease token by default. The gateway stores only its SHA-256 and grants a bounded lease per memory stream. Push requests carry the lease token separately from the encrypted event envelope.

This avoids silent last-write-wins semantics before conflict behavior has been benchmarked. Multi-writer/CRDT behavior is explicitly deferred.

## Encrypted event contract

`MemorySyncEvent` contains only bounded synchronization metadata plus ciphertext. Plaintext memory content is not a server API field.

Important invariant groups:

- identity: stream, event ID, idempotency key, device, device sequence;
- causality: aggregate ID/revision, parent event, previous device chain hash;
- optional cognitive correlation: turn/thought opaque IDs only;
- cryptography: algorithm/provider contract, key version, nonce, AAD hash, ciphertext SHA-256;
- timestamp: event creation time.

The default client crypto provider is XChaCha20-Poly1305 through PyNaCl/libsodium. Key material is resolved through a key-provider boundary and is never returned by status endpoints.

libsodium sources:
- <https://doc.libsodium.org/secret-key_cryptography/aead/chacha20-poly1305/xchacha20-poly1305_construction>
- <https://doc.libsodium.org/password_hashing/default_phf>

## Pull and materialization

Remote code never sends SQL to the client. Pull returns ordered encrypted events. The local client:

1. verifies remote sequence monotonicity and encrypted envelope contract;
2. stores/deduplicates an inbox row;
3. decrypts locally;
4. validates the versioned domain payload;
5. materializes through canonical `MemoryTierStore` APIs;
6. records conflicts explicitly;
7. advances the local cursor only after successful materialization.

A malformed or conflicting event blocks cursor advancement past that event. Unknown event types fail closed.

## Snapshot and restore

Cloud event replay is complemented by verified snapshots.

Snapshot creation:

1. operator stops the Jaźń daemon for a coherent multi-database generation;
2. each complete SQLite database is copied with Online Backup API;
3. staged databases pass SQLite integrity/FK checks;
4. files are streamed into bounded chunks;
5. chunks are compressed and encrypted on the client;
6. ciphertext objects are content-addressed and immutable;
7. the manifest binds stream, generation, `base_remote_seq`, device-chain head and every chunk;
8. the manifest is committed only after all referenced immutable objects exist.

Restore always writes to a fresh staging root. It verifies object identity, AEAD, plaintext hash/size/order and SQLite integrity. It never overwrites/promotes an active memory root automatically.

Object storage is an implementation detail behind `MemorySnapshotBackend`. S3-compatible storage is the first adapter. AWS documents that client-side encryption encrypts data before S3 receives it, that Object Lock provides WORM protection for object versions, and that S3 does not offer atomic multi-key updates. Consequently Jaźń uses immutable content-addressed objects and a transactional manifest/metadata store rather than a mutable `memory.zip` object.

Sources:
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingClientSideEncryption.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html>

## Gateway storage model

The deployable gateway has two provider-neutral storage boundaries:

- PostgreSQL repository: memory streams, encrypted event envelopes, monotonic sequence, snapshot manifests and writer leases;
- S3-compatible object store: immutable encrypted snapshot chunks.

PostgreSQL and S3 libraries are server-only optional dependencies. Local Jaźń in mode `off` does not import or require them.

Production deployment should use TLS. PostgreSQL server-side Row-Level Security can be used as defence in depth when multiple memory streams/users share a metadata database; absence of a policy after enabling RLS is deny-by-default in PostgreSQL.

Sources:
- <https://www.postgresql.org/docs/current/ssl-tcp.html>
- <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>

## Daemon ownership

`MemorySyncController` is the only automatic scheduler. It does not own memory truth; it schedules `MemorySyncRuntime.sync_once()`.

Properties:

- mode `off` means no thread/network;
- one synchronization cycle at a time;
- pause before starting a cycle while a user turn/runtime job is active;
- bounded shutdown wait;
- exceptions become sync diagnostics and never kill the daemon;
- local dialogue remains allowed under every cloud controller state.

`JaznDaemonServer` exposes controller status independently from its own liveness/readiness.

## Sidecar/wake truth

The normalization sidecar remains a derived continuity artefact. Existing normalization-run logical fingerprints are the source identity contract. `WakeStateRuntimeBridge` must pass the canonical `build_wake_state_status()` freshness gate before it may hydrate L1.

This closes a split-brain case where diagnostics could know that source memory changed while a lower-level bridge accepted an old normalization run. Missing/stale sidecar means continuity context is unavailable/rebuild-required; it does not erase healthy searchable canonical memory.

## Sandbox memory package v3

The v3 memory package fixes the current 8+ GiB raw JSONL failure without weakening ZIP safety limits.

Correct order:

```
normal local memory
→ verified SQLite snapshot / logical raw segmentation
→ memory manifest v3
→ memory.zip
→ optional binary split .001/.002 for ChatGPT upload
→ sandbox join
→ ZIP/member verification
→ attach
→ reconstruct raw segments in staging
→ validate/recover/deep-verify
```

Oversized raw JSONL is segmented before ZIP creation into bounded logical members. Each segment records index, byte size, SHA-256 and exact line range; reconstruction is verified byte-for-byte against the original source SHA-256/size/count. Binary splitting of a completed ZIP is never treated as logical segmentation.

## Status/truth fields

At minimum operator diagnostics distinguish:

- local memory/store status;
- continuity/wake status;
- cloud configuration readiness;
- crypto/key readiness;
- remote probe readiness;
- outbox/inbox/conflict/cursor state;
- controller enabled/running/degraded state;
- snapshot/restore verification.

A successful upload does not prove restore. A committed snapshot does not prove continuity. A cloud outage does not prove local memory failure.

## Rollout gates

1. **backup-only** — encrypted push, no remote materialization;
2. **verified restore drills** — restore repeatedly into an empty staging root and compare canonical memory state;
3. **single-writer push/pull** — enable ordered recovery/materialization with lease;
4. **durable L2/L3 canonical copy** — only after repeatable restore/fault tests;
5. **multi-writer** — separate future project after explicit conflict benchmark.

## Release acceptance

A release is not complete unless:

- local mode `off` works without cloud extras/credentials/network;
- cloud failure cannot reject a local memory transaction or dialogue turn;
- retry after lost ACK is idempotent with the same persisted ciphertext;
- pull never executes remote SQL and never advances past a failed/conflicting event;
- push/pull does not bypass L3 promotion decisions;
- plaintext memory is absent from gateway protocol fields/loggable status;
- snapshots use Online Backup API and restore only to staging;
- sidecar freshness is checked before L1 wake hydration;
- sandbox v3 creates no member above its configured safety limit;
- all active Python compiles, Pyright is clean, semantic/cognitive audits pass, full deterministic pytest is green, Windows targeted tests are green and package smoke/finalization passes.
