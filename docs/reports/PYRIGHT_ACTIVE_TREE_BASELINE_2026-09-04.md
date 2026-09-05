# Pyright active-tree baseline — 2026-09-04

## Scope

Branch: `fix/checkpoint-2026-09-04-master-corrected-pylance-pyright-hardening`

Baseline commit: `234da527b74471272c3eb7721037ca0ef6dc1126`

Pinned checker: `pyright 1.1.411`, Python `3.12`, Ubuntu runner.

Canonical scope comes from `pyrightconfig.json`:

- `latka_jazn`
- `tests`
- `tools`
- `main.py`
- `run.py`
- exclusion: `**/archive/**` only

Workflow run: `33850873738`

Result: **830 files analyzed, 18 errors, 0 warnings, 0 information**.

## Classification before fixes

The 18 emitted diagnostics reduce to 11 root-cause locations/groups. No diagnostic originates from an excluded archive path.

| Emitted diagnostics | File / locations | Rule | Classification | Root cause / intended correction |
|---:|---|---|---|---|
| 2 | `tests/test_dependency_unpacked_wheel_bootstrap_v1632555.py:179` | `reportArgumentType` | test typing | `files` is declared as `list[dict[str, object]]`, so `item["size_bytes"]` is only `object`; keep the size as an `int` while constructing the fixture instead of converting an arbitrary `object` later. Pyright emitted the same location twice. |
| 4 | `tests/test_memory_rebuild_v4_protocol_engine.py:651-654` | `reportArgumentType` | test typing | The synthetic `Dialogs` object exposes only `message`, but production `_run_test` requires the full structural `DialogBackend` protocol. Replace the partial double with a silent implementation that genuinely satisfies the protocol. |
| 1 | `tests/test_release_metadata_semantics_v163253.py:53` | `reportRedeclaration` | test typing | `_remove_git_metadata` is declared twice in the same test module. Keep the shared Windows-read-only implementation and remove the duplicate declaration. |
| 2 | `tools/memory_rebuild_legacy_v24.py:258-259` | `reportAttributeAccessIssue` | environment | `ctypes.windll` is Windows-only, while the canonical audit executes on Linux. Keep the Windows behavior but make the Windows-only function guard its own platform boundary using a type-checker-recognized `sys.platform` condition. |
| 4 | `tools/memory_rebuild_legacy_v24.py:709,924,1186,1343` | `reportArgumentType` | real bug | Prompt Toolkit accepts `AnyFormattedText`; its canonical tuple alias is `StyleAndTextTuples`, which includes both 2-tuples and optional mouse-handler 3-tuples. The local functions are annotated as invariant `list[tuple[str, str]]`; use Prompt Toolkit's own type alias for the callback return contract. |
| 3 | `tools/pack_generator_sources/jazn_pack_generator_v89.py:71,72,93` | `reportAttributeAccessIssue` | real bug | A module created dynamically with `importlib.util.module_from_spec` is statically a `ModuleType`; direct assignment to runtime-added attributes is not part of that static contract. Use explicit dynamic `setattr` for attributes intentionally installed on the module. |
| 2 | `tools/pack_generator_sources/jazn_pack_generator_v89.py:270-271` | `reportOptionalMemberAccess` | real bug | `manifest.get("target")` is evaluated more than once, so narrowing from one call does not prove the other call is a dict. Bind once, narrow once, then access `.get`. |

Category totals by emitted diagnostic:

- **test typing:** 7
- **environment/platform:** 2
- **real bug / active-code typing contract:** 9
- **archival code:** 0

## Local VS Code-only `rarfile` diagnostic

The user-reported `reportMissingImports` for `rarfile` did **not** reproduce in the controlled audit. The workflow installed the project from `pyproject.toml`, installed `rarfile>=4.5,<5`, and `python -m pip check` reported no broken requirements. It is therefore classified as a local selected-interpreter / `.venv` environment issue unless a later controlled run demonstrates otherwise.

## Fix policy

- Do not weaken Pyright/Pylance rules.
- Do not add blanket ignores.
- Preserve the production `DialogBackend` contract.
- Preserve archive snapshots; only active files are corrected.
- Re-run pinned Pyright after the minimal corrections, then run compileall and the deterministic pytest suite.
- Synchronize release metadata only after code and validation changes settle.
