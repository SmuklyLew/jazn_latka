# Independent memory package contract v3

## Purpose

This contract exists only for verified transfer of Jaźń memory into constrained environments such as the ChatGPT sandbox. It is not a local runtime storage format and does not replace local SQLite.

Schema: `jazn_memory_package_manifest/v3`.

## Core rules

- Memory packages are data transports and never become `active_root`.
- Runtime version recorded in a standalone memory package is provenance, not a strict compatibility equality check.
- Each SQLite shard in the package is a complete point-in-time SQLite database produced through the SQLite Online Backup API. A binary fragment of a `.sqlite3` file is not a usable shard.
- SQLite snapshots have a dedicated transport-member limit (default 1 GiB). Exceeding it fails closed and requires shard/rollover; it never enables binary splitting of the database.
- Raw JSONL segments have their own bounded member limit (default 480 MiB), below the general ZIP safety ceiling.
- Each ZIP member is still bounded by the global package-member safety limit.
- Large raw JSONL streams are logically segmented before ZIP creation.
- Binary `.001/.002/...` split parts may be created only after the logical ZIP is complete and are only upload transport fragments.
- Attach verifies the manifest in staging and reconstructs segmented raw sources before activation.
- Derived sidecars/indexes never outrank canonical source memory and must be discarded/rebuilt when source identity does not match.

## Raw segment descriptor

A v3 manifest descriptor records:

- canonical `source_path`;
- original byte size and SHA-256;
- exact source line count;
- segment target/hard limits;
- ordered segment descriptors with package path, index, size, SHA-256 and line range.

Reconstruction concatenates segment bytes in order into a temporary file, verifies every segment and the final source identity, fsyncs the reconstructed file and only then atomically replaces the destination. On failure the temporary file is removed and the original staging state is not promoted.

## Backward compatibility

The reader continues to recognize legacy v1/v2 manifests according to their historical truth boundaries. New memory exports use v3. Existing security limits are not relaxed to accept oversized legacy members. Such a package must either be re-exported with logical segmentation or migrated with `run.py memory-repack-legacy`, which verifies the legacy package set before transforming raw JSONL and SQLite into v3-safe transport members.

## Transport sources

A standalone v3 memory package may enter `memory-attach` from either:

1. a local directory containing the package sidecar and all declared ZIP parts; or
2. a private Cloudflare R2 prefix exposed through the S3-compatible API.

The R2 path is not a second activation mechanism. The client lists a flat package-set prefix, requires exactly one `profile=memory` sidecar, streams only the sidecar-declared objects into local staging, and checks declared object sizes and SHA-256 while downloading. The staged package then enters the same canonical local verification and activation path as `--parts-dir`: package-part SHA, ZIP CRC/resource/path checks, exact extracted tree, memory manifest, SQLite integrity, raw-segment reconstruction, previous-memory backup and transactional-memory initialization. Cloud availability therefore never becomes a precondition for an already installed local runtime.

The memory sidecar advertises `cloud_attach_compatible=true`, `memory_transport_contract=jazn_memory_package_transport/v1`, and a flat `s3_compatible` object layout. Credentials are not stored in the package.

## ChatGPT transfer sequence

1. build a verified memory snapshot/export locally;
2. build v3 `memory.zip`;
3. verify ZIP CRC and sidecar hashes;
4. optionally split the completed ZIP for upload;
5. upload all parts and package metadata;
6. join parts in sandbox;
7. verify joined ZIP SHA-256;
8. inspect/verify v3 manifest and resource limits;
9. attach to a stopped runtime staging root;
10. validate/recover/deep-verify;
11. rebuild/verify derived sidecar/wake state;
12. start runtime and verify continuity truth gates.
