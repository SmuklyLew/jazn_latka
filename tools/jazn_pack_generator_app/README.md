# Jaźń Pack Generator 10.1.86.0.112

Active implementation of `tools/jazn_pack_generator.py`.

## Scope

The tool archives a selected Jaźń folder as one logical ZIP. It has three
content modes: `system`, `memory` and `system+memory`. A logical ZIP may stay as
one normal ZIP or be split after successful ZIP/CRC creation into binary
transport parts (`.zip.001`, `.002`, ...), default 450 MiB.

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

## Safety

- ZIP64 is enabled.
- archive member names are validated for traversal, Windows reserved names and
  case-insensitive collisions;
- symlinks and Windows junctions fail closed;
- output cannot be inside the system or memory source;
- staging is used before the final directory commit;
- CRC and SHA-256 are verified;
- split packages have logical and per-part SHA-256 sidecars;
- extraction is staged and committed only after preflight.

## Integralność 10.1.86.0.112

Przed zapisem ZIP generator tworzy tymczasowy canonical release staging jako kopię
bajt-w-bajt. Dla plików SYSTEM sprawdza politykę EOL z `.gitattributes` i kończy
operację błędem przy drift LF/CRLF. Każdy plik ma SHA-256 w manifestcie v2, a
weryfikator ponownie liczy SHA-256 bezpośrednio z wpisów ZIP.
