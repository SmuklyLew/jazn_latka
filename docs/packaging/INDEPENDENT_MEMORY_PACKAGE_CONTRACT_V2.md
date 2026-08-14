# Independent Memory Package Contract v2

## Status

Feature contract for `feat/independent-memory-package-contract-v2`.

This contract separates the lifecycle of the Jaźń system package from the lifecycle of Łatka memory packages. A memory package is data and can never become an `active_root` by itself.

## System vs memory

The system package remains strict and release-bound. Its `latka_jazn/version.py`, `PACKAGE_INTEGRITY_MANIFEST.json`, `SOURCE_PROVENANCE.json`, start file and package sidecar must describe the same runtime.

A standalone memory package uses `memory/MEMORY_PACKAGE_MANIFEST.json` with:

- `schema_version = jazn_memory_package_manifest/v2`;
- `memory_format_version = 2`;
- a UUID `snapshot_id`;
- a timezone-aware `created_at_utc`;
- `created_with_runtime` as provenance only;
- `compatibility.contract = jazn_memory_runtime/v1`;
- `compatibility.runtime_version_is_provenance_only = true`;
- SHA-256 and size for every packaged memory file;
- verified metadata for every SQLite database snapshot.

A difference between `created_with_runtime` and the current runtime is therefore an advisory provenance signal, not a package rejection reason. Rejection is based on unsupported memory contract/schema, unsafe paths, missing or extra files, SHA/size mismatch, invalid SQLite, or inconsistent database metadata.

## SQLite snapshot rule

Standalone memory packaging must not copy a live SQLite database file while ignoring its WAL. The generator creates a point-in-time database through the SQLite Online Backup API, validates the snapshot with `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, then hashes and archives the snapshot. `-wal` and `-shm` files are never packaged.

For each SQLite database the v2 manifest records at least:

- path and logical role;
- `snapshot_method = sqlite_online_backup_api`;
- `PRAGMA user_version`;
- `PRAGMA application_id`;
- SHA-256 of the canonical SQLite schema;
- table count;
- file size and SHA-256;
- integrity and foreign-key validation result.

## Legacy v1

`jazn_memory_package_manifest/v1` remains readable as a migration/compatibility format. A differing `runtime_version` becomes an advisory warning. File hashes and SQLite structural integrity remain mandatory. Because v1 did not prove how SQLite was snapshotted, the loader reports that historical WAL completeness is unverifiable when a legacy package contains SQLite.

## Combined package compatibility

`combined` is intentionally not the independent transport path. To preserve the existing strict `runtime-bootstrap` contract, the generator keeps an embedded v1 memory manifest bound to the system carried in the same combined archive. The SQLite bytes are still produced through the safe Online Backup snapshot path.

Standalone `memory` and the memory half of `dual` always use v2.

## Attachment workflow

Canonical standalone attachment is:

```text
python -X utf8 run.py memory-attach \
  --root <VERIFIED_SYSTEM_ROOT> \
  --parts-dir <MEMORY_PACKAGE_DIR> \
  [--zip-name <MEMORY_ZIP_NAME>]
```

The operation is fail-closed:

1. verify the installed system independently;
2. refuse attachment while the runtime daemon is active;
3. require a current package sidecar whose profile is exactly `memory`;
4. verify part hashes and ZIP CRC;
5. extract to staging with existing traversal/symlink/duplicate protections;
6. require a memory-only extracted tree;
7. verify the v1/v2 memory manifest and all SQLite databases;
8. materialize a candidate under `workspace_runtime/memory_attach/`;
9. atomically swap `memory/` with rollback on post-install verification failure;
10. write `workspace_runtime/MEMORY_ATTACH_CURRENT.json` only after success.

`memory-attach` does not start the daemon and does not promote L2/L3 records. The runtime should be started only after attachment and normal memory/wake-state validation.

## Truth boundary

Packaging and attachment verify transport integrity and SQLite structural health. They do not turn raw conversations into semantic facts, approve identity claims, or promote L2/L3 memory. Those remain responsibilities of the existing memory normalization, truth and promotion contracts.
