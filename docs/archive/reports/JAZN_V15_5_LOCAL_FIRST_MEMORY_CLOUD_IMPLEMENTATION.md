# Jaźń v15.5 candidate — local-first memory/cloud implementation report

## Implemented on branch

`upgrade/local-first-memory-cloud-v155` separates normal local memory, optional encrypted cloud durability and ChatGPT sandbox packaging.

The implementation adds complete owner components rather than placing network calls or small cloud helpers into the local memory hot path:

- `MemorySyncRuntime` — configuration, key/crypto/backend composition and explicit one-shot sync;
- `MemorySyncController` — daemon-owned background scheduler, fail-soft and mode-aware;
- `CloudMemorySyncWorker` — transactional outbox push, exact-envelope retry, ordered pull, inbox/conflict/cursor handling;
- `MemorySyncStoreMixin` — durable replication ledger integrated into `MemoryTierStore`;
- `MemorySyncDomainMaterializer` — typed remote event materialization through canonical domain APIs;
- `PyNaClXChaCha20Poly1305Provider` and snapshot crypto provider — client-side authenticated encryption behind protocols;
- `SQLiteMemorySnapshotManager` — Online Backup, integrity verification, bounded encrypted chunks and staging-only restore;
- `MemoryCloudSnapshotRuntime` — operator-facing multi-database snapshot/restore controller;
- `MemoryCloudGatewayService`/WSGI application — authenticated encrypted wire gateway;
- `PostgresMemoryCloudRepository` — monotonic sequence, immutable event identity, snapshot manifests and writer leases;
- `S3CompatibleObjectStore` — immutable content-addressed encrypted objects;
- `MemoryCloudServerFactory` — server deployment composition root with lazy optional dependencies;
- `RawMemorySegmenter` — exact streaming segmentation/reconstruction for sandbox transports.

## Preserved safety boundaries

- default local mode is `off` and performs no cloud network work;
- local memory commit occurs before and independently of remote durability;
- cloud failure never marks local dialogue/runtime as unavailable;
- L3 promotion continues to require the existing promotion contract;
- pull never executes remote SQL;
- full private Cognitive State Graph content is not a cloud protocol payload;
- status endpoints do not expose bearer, lease or memory encryption keys;
- `WakeStateRuntimeBridge` now consults the canonical source-freshness gate before hydrating a wake snapshot;
- ZIP segmentation is restricted to sandbox packaging and does not change local storage architecture.

## Verification strategy

The branch contains deterministic tests for:

- outbox idempotency and lost ACK after remote commit;
- exact encrypted envelope reuse on retry;
- push/pull materialization without echo outbox;
- cursor conflicts and fail-closed event types;
- writer lease ownership;
- daemon sync scheduling/fail-soft behavior;
- real XChaCha round-trip when the optional dependency is installed;
- encrypted snapshot creation/restore and integrity failures;
- WSGI client/gateway encrypted event and snapshot round trips;
- server composition with injected providers;
- logical JSONL segmentation/reconstruction and member limits;
- v1/v2 backward compatibility plus v3 package verification;
- source-change rejection by runtime wake hydration;
- local-first architecture boundaries.

GitHub release CI installs the `memory-cloud` extra so the real PyNaCl tests run instead of being skipped. Server provider libraries remain in the `memory-cloud-server` extra and are lazily imported so normal local Jaźń does not depend on PostgreSQL/S3 packages.

## External engineering basis

- SQLite network/filesystem guidance: <https://www.sqlite.org/useovernet.html>
- SQLite Online Backup API: <https://www.sqlite.org/backup.html>
- PostgreSQL TLS: <https://www.postgresql.org/docs/current/ssl-tcp.html>
- PostgreSQL Row-Level Security: <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
- libsodium XChaCha20-Poly1305: <https://doc.libsodium.org/secret-key_cryptography/aead/chacha20-poly1305/xchacha20-poly1305_construction>
- libsodium password hashing/Argon2id: <https://doc.libsodium.org/password_hashing/default_phf>
- Amazon S3 client-side encryption: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingClientSideEncryption.html>
- Amazon S3 Object Lock: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html>
- Amazon S3 object consistency/multi-key limitation: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html>

These sources inform boundaries and storage behavior; the implementation remains provider-neutral at the Jaźń domain layer.
