# Jaźń v16.3.8 — archive I/O + package generator hardening

## Goal

Add one fail-closed archive layer shared by Jaźń tooling and package workflows, covering:

1. ZIP / ZIP64, including Jaźń binary split sets (`.zip.001`, `.002`, ...).
2. 7z, including verified binary split sets (`.7z.001`, `.002`, ...).
3. WinZip AES ZIP through `pyzipper`, with AES 128/192/256 and 256 as the default.
4. `pyzip` / `PyZipFile` inputs as ordinary ZIP aliases rather than a new container format.

## Architecture

`latka_jazn.archive.ArchiveExtractionService` is the canonical archive boundary. It:

- detects ZIP versus 7z by signature rather than extension;
- detects AES ZIP from ZIP extra fields when possible;
- lazily uses `py7zr` for 7z and `pyzipper` for AES ZIP;
- verifies sidecar part size/SHA-256 and package-set SHA-256;
- joins binary split sets only after every part is verified;
- verifies the logical archive hash when provided;
- rejects absolute paths, traversal, Windows ADS/reserved names, symlinks, special files, duplicates and case-insensitive collisions;
- enforces member count, per-member size, total uncompressed size and compression-ratio limits;
- checks free disk space by default;
- extracts to a fresh sibling staging tree;
- verifies extracted sizes and sidecar SHA-256 values;
- publishes via atomic rename with rollback when replacement was explicitly requested.

`tools/jazn_archive.py` exposes the service as a deterministic JSON CLI for inspect, extract and pack operations.

## Password boundary

Passwords are never written to package sidecars, generator settings, logs, filenames or command examples. Tools accept only a **password environment-variable name**; the secret value is read at execution time. AES ZIP creation requires a password. 7z encryption is opt-in at the generator policy level.

## Generator integration

The public `tools/jazn_pack_generator.py` keeps the historical v8.5 API surface for compatibility while loading the v16.3.8 archive-I/O policy. Existing ZIP output remains the default. New settings are stored under the `archive_io` object in `jazn_pack_generator_settings.json` and can be edited with `archive-settings` or command flags.

The existing `archive_format` setting continues to mean the **volume layout** (`auto`, `independent`, `binary`). The new `container_format` means the actual container (`zip`, `7z`, `aes_zip`). This avoids overloading one field with two unrelated semantics.

## Truth boundary

This update gives the Jaźń codebase the ability to perform archive operations when its Python process can access the files. It cannot make a ChatGPT host execute local code when the platform's own executor is unavailable. Host/runtime liveness remains a separate boundary.
