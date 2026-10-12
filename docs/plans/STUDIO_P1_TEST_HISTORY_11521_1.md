# P1 — Test Studio run-history & bounded JSON export (v16.3.25.5.115.21.1)

Parent branch: `upgrade/v16.3.25.5.115.21.0-studio-config-preview-p1` (PR #344); this is a stacked, **partial P1** slice. Do not merge before parents are accepted.

## Implemented

- One automatic, bounded redacted summary of each finished Test Studio pytest run; all UI modes use the same runner. The record is separate from pytest outcome and does not store output, CLI arguments, node IDs, prompts, absolute paths, MEMORY/SQLite material.
- Cross-process serialized history writing reuses the existing Jaźń guard. Atomic create/replace of a validated leaf in the per-system operator directory, retention of 100 entries and size cap 256 KiB.
- Read-only history CLI with `history --limit`, explicit create-only `history-export --output` rejecting SYSTEM/MEMORY/workspace targets or overwriting existing files.
- Read-only History tab in Tk window. No new daemon, memory adapter, or model code.
- Studio version 1.4.0, SYSTEM version 16.3.25.5.115.21.1, release name `studio-test-history-p1`.
- New synthetic unit tests for isolation, no creation on discovery, redaction, retention, format violations, symlinks, explicit export and safe path bounds; 5 edited version-pinned tests archived byte-identically.

## Acceptance

Full deterministic pytest, Pyright, compileall, Test Studio contract catalog generator, canonical release metadata, Windows/Linux GitHub workflows and package smoke. CI determines pass/fail; a stored commit is not acceptance.

## Not covered by this slice

Memory Studio source/target/staging/active comparison and readiness, Configuration Studio effective runtime activation, remaining P1 test result analysis/timeout/STOP refinements, P2 forms and packaging stages, P3 Version Rebuild. No real-host ChatGPT accepted turn proof.

The implementation follows Python's official subprocess guidance to separate child-process completion and timeout handling: https://docs.python.org/3/library/subprocess.html. GitHub Actions and code tests, rather than history file existence, remain sources of test-result truth.
