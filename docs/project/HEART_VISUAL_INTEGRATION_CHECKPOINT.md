# Heart System integration — audit and visual workbench

## Integrity boundary

The canonical manifest hashes Git object bytes. A clean, ordinary checkout is
verified against those objects; Git's declared CRLF conversion on Windows is
therefore permitted without relaxing any hash. Dirty, flagged or exported
trees use exact filesystem bytes. In that mode the same CRLF files correctly
fail a manifest protecting LF bytes. Never normalize inputs inside the hash
validator or treat a dirty checkout as verified release source.

The previous report of 13 Windows script mismatches was taken while generated
metadata was dirty. The clean 39e7a468 checkpoint verifies successfully through
`canonical_git_head_blobs`. No script rewrite or attributes change is needed.
Existing canonical-worktree tests protect clean CRLF, dirty tampering, strict
exports and a failing Git batch. They remain unchanged.

Version-bound JSON contracts may serialize only their declared top-level
version field. The audit verifies exact agreement with version.py, rejects
missing/stale values, malformed JSON and duplicate fields, and still scans
every other field for forbidden release literals. This is not a file exemption.

## Integration matrix

| Stage | State / remaining acceptance |
| --- | --- |
| P0 | fc500058 retained; live daemon/model acceptance still separate |
| Audit integrity | Clean Git canonical verification PASS; strict dirty/export byte policy retained |
| P1 | Central visual system and operator shell in implementation; whole-application operator acceptance required |
| P2 | ConPTY/PTY interactive terminal remains open; task consoles retain their explicit identity |
| P3 | Existing canonical service controls retained; complete service acceptance remains open |
| P4 | Twelve-Studio operational parity remains open per STUDIO_MIGRATION.md |
| P5 | Final-source CI, physical DPI/keyboard, offline EXE and AV acceptance remain separate gates |

No new dependencies, private MEMORY migration, daemon ownership or deployment
is authorized by this visual work. Preserve the Draft state of PR #436.
