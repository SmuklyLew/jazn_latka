# Pack Generator archive before 10.1.86.0.113

This directory is an immutable historical snapshot created while restoring the
Jaźń Pack Generator to its primary selected-folder ZIP contract.

Source base: `master` commit `4722332abcb36cc573ef489cbc9ac0bdca26cd58`
(previous release `16.3.25.5.26-package-generator-v10.1.86.0.112-byte-exact-eol-staging`).

Archived here:

- `tree/tools/pack_generator_sources/` — retired pre-10.1.86.0.111 generator
  implementation lineage. Its own README already declared that active code had
  moved to `tools/jazn_pack_generator.py` + `tools/jazn_pack_generator_app/`.
- `tree/tests/test_jazn_pack_generator_v101860112_byte_exact_staging.py` — the
  superseded active v112 contract that made EOL drift fail closed.
- `tree/docs/runtime/JAZN_PACK_GENERATOR_V101860112_BYTE_EXACT_STAGING.md` — the
  superseded v112 runtime documentation.

Active tests which still protect public API, archive safety, UI modes, content
profiles or memory transport are intentionally **not** retired merely because
their filenames contain older version labels.

Existing `tests/archive/` snapshots are intentionally not moved: that directory
is append-only evidence and its own README forbids moving, renaming or editing
existing snapshots.
