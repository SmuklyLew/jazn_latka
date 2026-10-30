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
| P1 | Shared tokens, six-profile palette, dialogs, responsive controls, tables, ten menus, command palette, activity bar, section tabs and v2 bounded layout implemented; whole-application operator acceptance required |
| P2 | ConPTY/PTY interactive terminal remains open; task consoles retain their explicit identity |
| P3 | Existing canonical service controls retained; complete service acceptance remains open |
| P4 | Twelve-Studio operational parity remains open per STUDIO_MIGRATION.md |
| P5 | Final-source CI, physical DPI/keyboard, offline EXE and AV acceptance remain separate gates |

No new dependencies, private MEMORY migration, daemon ownership or deployment
is authorized by this visual work. Preserve the Draft state of PR #436.

## Visual implementation

`workbench_theme.py` owns color/typography/spacing/density/focus tokens and
contrast calculations. The custom accent is preserved; selected text and focus
choose readable contrasting colors even for black/white accents. Semantic
success/warning/error colors have separate light/dark variants.

`visual_system.py` applies a scoped Qt palette and stylesheet to the window,
all existing pages and parented dialogs, and observes newly created controls.
Forms wrap long rows; action rows stack when needed; long button labels wrap
without losing their dynamic state or full tooltip. Tables use alternating
rows, movable headers, pixel scrolling and full-text hover tooltips. Existing
specialized table sizing and read-only contracts remain intact.

`workbench_shell.py` provides Plik/Edycja/Widok/Terminal/Usługi/Jaźń/Studia/TPA/
Narzędzia/Pomoc. Ctrl+Shift+P filters real actions; Enter executes the selected
action through the existing guard. Menus retain canonical confirmation and
capability errors. Missing native import/restore and embedded PTY are explicitly
identified as remaining stages. No fabricated terminal or readiness was added.

At narrow widths the activity rail and section tabs give way to existing search
and menus; the sidebar collapses while preserving the operator's preference.
At larger widths the activity rail, section tabs, splitters and docks remain
available. Layout v2 stores only bounded primitive dimensions and known-section
labels, migrates v1 and rejects unknown fields or unsafe sizes. Layout reset
preserves theme preferences instead of overwriting them with defaults.

This change covers the shared Qt presentation. Independently launched classic
Tk/cursor studios remain available and are not claimed to share the Qt theme
or to satisfy native parity. Physical DPI, screen-reader review, every Studio
workflow and operator acceptance are still open; automated renderings do not
promote any full_gate to PASS.
