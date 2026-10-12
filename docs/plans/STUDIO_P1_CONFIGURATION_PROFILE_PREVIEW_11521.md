# P1 slice: Configuration Studio read-only profile preview — 16.3.25.5.115.21.0

**Status: PARTIAL P1 / Draft.** Parent: `fix/v16.3.25.5.115.20.2-mcp-probe-p0` (PR #343). Full seven-Studio program remains governed by `docs/plans/STUDIO_MODERNIZATION_PROGRESS.md` (issue #340). Do not merge before the P0 parent is accepted.

## Implemented in this slice

- The Configuration Studio operator profile editor can show a **read-only**, normalized dry-run diff before save.
- Snapshot digest is checked before the preview (same CAS guard as save); stale editor state is rejected.
- Each allowlisted setting reports its saved override, proposed override, change flag and future-launch provenance. Undefined defaults and inherited runtime effective values stay **unknown** rather than manufactured.
- Existing read-only runtime marker is a warning for changes to MEMORY/workspace placement, **not** proof of runtime readiness.
- The preview does not write profiles, MEMORY, SQLite or daemon state, execute activation, or claim that a future-launch profile is already active.
- UI is a local Tk preview window; no threads or new lifecycle introduced.
- Historical source versions of five edited release-identity tests preserved byte-identically under `tests/archive/v16.3.25.5.115.20.4-pre-studio-p1/`.

## Required CI

- Test: `python -X utf8 -m pytest -q tests/test_configuration_studio_p1_preview.py tests/test_configuration_studio.py`
- Full deterministic suite, Pyright, `compileall`, Windows GUI imports, Test Studio catalog sync, canonical release metadata sync.
- Parent PR #343 has an intermittent Windows runtime-health timing test (5.018 s vs <5 s); P1 must not hide or relax this P0 gate.
- Real operational profile activation and real-host ChatGPT MCP tool exposure are NOT proved by these read-only tests.

## P1 not yet implemented

- Verified defaults/effective running-process configuration lineage; activation workflow with independent runtime-stop verification.
- Memory Studio source/target/staging/active comparison/readiness pages.
- Test Studio filtering/history/export/timeout/STOP improvements.

P2 remains unstarted: Dependency/Python Runtime Studio forms and Pack Generator staging/publication controls. P3 remains unstarted: Version Rebuild Studio restructuring.
