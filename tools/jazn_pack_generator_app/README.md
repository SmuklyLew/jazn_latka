# Jaźń Pack Generator 10.1.86.0.114

Active implementation of `tools/jazn_pack_generator.py`.

## Primary scope

The tool has two explicit byte contracts. Runnable **SYSTEM** content is materialized from canonical release staging (Git blobs for a checkout, verified-export bytes without Git). **MEMORY** remains a selected-folder byte-exact snapshot. The primary archive format is one ordinary logical ZIP.

The user chooses whether that logical ZIP remains:

- one normal `.zip` file, or
- one logical ZIP split after creation into binary transport parts
  (`.zip.001`, `.002`, ...), default 450 MiB.

Joining the binary parts recreates the original logical ZIP byte-for-byte.

Content modes remain `system`, `memory` and `system+memory`.

It intentionally does **not** build dependency wheelhouses, Python runtimes or
platform-specific distributions.

## Interfaces

- `--ui text` — classic terminal flow.
- `--ui tui` — cursor-driven terminal interface; falls back to text when no TTY is available.
- `--ui studio` — native Tk/ttk application with Start, Packing, Unpacking,
  Verification, Settings, Configuration and Information pages.

All interfaces call the same `service.py` core.

## Mutable user settings

The default mutable file is
`tools/jazn_pack_generator_app/jazn_pack_generator_settings.json`. It is
gitignored. `JAZN_PACK_GENERATOR_SETTINGS` can point at another location.
`jazn_pack_generator_settings.example.json` is the tracked example.

`memory_rebuild_settings.json` is also local operator state and is excluded from
SYSTEM packages.

## Safety and integrity

- ZIP64 is enabled.
- Archive member names are validated for traversal, Windows reserved names and
  case-insensitive collisions.
- Symlinks and Windows junctions fail closed.
- The output cannot be inside the system or memory source.
- `.git`, `.archives`, runtime state, caches, local mutable settings and nested
  package artifacts are excluded from SYSTEM.
- MEMORY source files are copied to temporary staging **byte-for-byte** and changing files fail closed.
- SYSTEM is materialized through the canonical release staging contract; checkout EOL bytes are not release input.
- CRC and per-member SHA-256 are verified after ZIP creation.
- SYSTEM ZIPs are safely extracted into a fresh clean-room and their embedded package-integrity/provenance contracts are reverified before publication.
- Duplicate members, path traversal, symlinks and case-fold collisions fail closed.
- Manifest schema `jazn_pack_generator_package/v2` records SHA-256 for every
  packaged file.
- The verifier reads members back from ZIP and requires their SHA-256 to match
  the actual source/staging bytes.
- Split packages have logical and per-part SHA-256 sidecars.
- Extraction is staged and committed only after preflight.

## EOL policy in 10.1.86.0.114

For SYSTEM, `.gitattributes` defines checkout behavior but the working tree is not the release byte source. Git text can be LF in the index and CRLF in the working directory; `create_release_staging()` reads canonical Git blobs, so any working-tree EOL drift is bypassed rather than accepted into a runnable release.

For MEMORY, `.gitattributes` remains diagnostic only and snapshot bytes are preserved exactly.

See `docs/runtime/JAZN_PACK_GENERATOR_V101860114_CANONICAL_SYSTEM_RELEASE.md`.
