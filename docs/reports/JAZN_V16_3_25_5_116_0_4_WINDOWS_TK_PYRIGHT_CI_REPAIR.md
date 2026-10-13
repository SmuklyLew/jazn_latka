# Jaźń v16.3.25.5.116.0.4 — Windows Tcl/Tk CI and Pyright gate repair

Date: 2026-10-13. Forked from PR #360 branch SHA `806e94e0028072f7956c32721455e1bb47828af1`.

## Root cause and exact evidence

- GitHub Actions [38352567563](https://github.com/SmuklyLew/jazn_latka/actions/runs/38352567563), full PowerShell deterministic suite: **2491 passed, 9 skipped, 1 failed**. The only failure was `tests/test_configuration_studio_gui_windows.py::test_gui_refuses_to_discard_unsaved_edits`, during `tk.Tk()`, **before application assertions**. Hosted CPython 3.12.10 Tcl/Tk path `.../tcl/tk8.6/menu.tcl` was missing.
- GitHub Actions [38352406380](https://github.com/SmuklyLew/jazn_latka/actions/runs/38352406380), old commit `9dd15607`: Pyright **1 error, 0 warnings** because `ContextRuntimePort` declared `context` where `JaznEngine` accepted `client_context`. The forked current source already uses `client_context` in both protocol methods; the later [38352567677](https://github.com/SmuklyLew/jazn_latka/actions/runs/38352567677) / [38352561036](https://github.com/SmuklyLew/jazn_latka/actions/runs/38352561036) Pyright runs passed. No redundant port rename, no weakened rules.

## Implemented changes

1. Pin the failing Windows Tk environment to CPython `3.12.9` (published in official `actions/python-versions` Windows x64 distribution), instead of floating `3.12` that resolved to broken `3.12.10`.
2. New `tools/windows/check_tk_runtime.py`: verify required version-aware Tcl/Tk assets and initialize/destroy **two real Tk roots**. Missing files and failed initialization are **CI failures**, never skipped.
3. Run the two real Configuration Studio Tk tests in a separate, mandatory pytest process before the remaining Windows deterministic suite; the full suite omits just this already-executed file to avoid process-global Tk pollution. The UI test's assertions, coverage and failure policy remain intact.
4. Apply Tk installation checks to the Configuration Studio Windows workflow for Python 3.12.9 and 3.14, including the packaged GUI build test.
5. Update package version to `16.3.25.5.116.0.4` with startup/deployment release contracts and five version-bound active tests; preserve original test bytes in `tests/archive/v16.3.25.5.116.0.3-windows-gate-source`.
6. Use release-hardening `manifest_sync` for authoritative regeneration of Test Studio catalog, package manifest and source provenance. Do not hand-edit hashes or relax Pyright.

## Acceptance gates

- Full zero-error, zero-warning Pyright on the **new** head.
- Windows PowerShell separate real GUI tests + full deterministic suite, both mandatory and successful.
- Configuration Studio Windows matrix 3.12.9 + 3.14; Windows packaged GUI smoke.
- Ubuntu + Windows release-hardening and canonical metadata sync.
- Clean checkout; no private MEMORY or running runtime mutation.

This document does not claim final CI pass before the runs complete. PR is Draft and must not be merged merely because GitHub reports mergeable.

## References

- https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md (exact patch version downloads)
- https://github.com/actions/setup-python/issues/1102 (Windows hosted Tcl initialization issue)
- https://github.com/microsoft/pyright/blob/main/docs/type-concepts-advanced.md
