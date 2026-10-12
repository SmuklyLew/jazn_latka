# Wake/session continuity hardening

## Problem

The runtime persisted dialogue/task state in a hash-bound session checkpoint, but restart verification treated that checkpoint as unusable whenever wake-state was unavailable. A missing normalization sidecar therefore cleared `last_user_text`, route, intent and `task_state`, even though the session checkpoint itself had already passed its state hash, checkpoint hash and session-id checks.

A second resilience gap was that `WakeStateRuntimeBridge.hydrate_l1()` reported `sidecar_missing` without attempting the canonical normalization/wake preparation path when the verified local recovery source database already existed.

## Repair

This change separates two claims that have different evidence:

1. **Dialogue/task checkpoint integrity** — the local persisted session payload is hash-bound and can continue when its checkpoint validates.
2. **Wake/autobiographical memory continuity** — this remains allowed only when a verified wake snapshot is available and matches the checkpoint binding.

If wake is unavailable rather than contradicted, the runtime now keeps the independently verified dialogue/task checkpoint but sets `memory_continuity_claim_allowed=false`. If two verified wake snapshots disagree, the existing fail-closed behavior remains: previous user text, route, intent and task state are cleared.

`WakeStateRuntimeBridge.load()` remains read-only by default. Operational `hydrate_l1()` may repair a missing derived sidecar only when `normalization_source_db_path` already exists locally. Repair delegates to `MemoryNormalizationSidecar.prepare(dry_run=False, force=False, deep_verify=True)`, which validates the source database, normalizes through the canonical SQLite path and validates the resulting wake snapshot. No source means no repair and no synthetic memory.

## Durability and validation basis

The existing session checkpoint writer continues to use a temporary file, file flush + `fsync`, and `os.replace()` for atomic replacement. Python documents `os.replace()` as a rename that replaces an existing destination and is atomic when successful on the same filesystem where POSIX atomic rename semantics apply:

- Python `os.replace`: https://docs.python.org/3/library/os.html#os.replace

The sidecar path continues to rely on SQLite transactions and the project’s existing integrity/foreign-key checks. SQLite documents atomic commit/recovery semantics and its integrity/FK validation pragmas here:

- SQLite atomic commit: https://www.sqlite.org/atomiccommit.html
- SQLite WAL: https://www.sqlite.org/wal.html
- SQLite PRAGMA `integrity_check` / `foreign_key_check`: https://www.sqlite.org/pragma.html

These sources support the storage/durability choices; they do not establish the application-level truth boundary. The latter is enforced explicitly by the runtime fields above.

## Truth boundary

This patch does **not** claim that missing memory has been recovered. It does not synthesize a wake snapshot, does not promote L2/L3, and does not turn a valid dialogue checkpoint into proof of autobiographical memory continuity. A system-only package with no recovered source database will still report wake unavailable, but it no longer has to discard an independently valid local task/dialogue checkpoint for that reason.
