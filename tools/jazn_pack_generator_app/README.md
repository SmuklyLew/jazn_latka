# Jaźń Pack Generator 10.1.86.0.113

Active implementation of `tools/jazn_pack_generator.py`.

## Primary scope

The tool archives the **selected Jaźń project/system folder** using the actual
bytes of files admitted by the explicit safety/exclusion policy. Its primary
archive format is one ordinary logical ZIP.

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
- Approved source files are copied to temporary staging **byte-for-byte**.
- Source files changing during staging fail closed.
- CRC and SHA-256 are verified after ZIP creation.
- Manifest schema `jazn_pack_generator_package/v2` records SHA-256 for every
  packaged file.
- The verifier reads members back from ZIP and requires their SHA-256 to match
  the actual source/staging bytes.
- Split packages have logical and per-part SHA-256 sidecars.
- Extraction is staged and committed only after preflight.

## EOL policy in 10.1.86.0.113

`.gitattributes` is repository/checkout policy, not the source of archive bytes.
When it is readable, Pack Generator may report LF/CRLF differences as
**diagnostics only**. EOL differences do not transform source bytes and do not
block a valid folder snapshot.

Therefore archive byte integrity means:

`SHA256(actual selected source bytes) == SHA256(bytes read back from ZIP)`.

A missing, unreadable or malformed `.gitattributes` does not prevent packing a
normal folder snapshot. This keeps the archiver usable for ordinary folders,
including copies that are not Git working trees.
