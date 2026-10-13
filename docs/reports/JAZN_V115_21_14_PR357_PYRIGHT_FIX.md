# Jaźń v16.3.25.5.115.21.14 — PR #357 CI repair

**Date:** 2026-10-13  
**Branch:** `upgrade/v16.3.25.5.115.21.13-code-first-runtime-documentation-convergence`  
**Status:** change submitted for CI, not production acceptance.

## Root cause and repair

GitHub Actions run [38333637745](https://github.com/SmuklyLew/jazn_latka/actions/runs/38333637745)
reported exactly one Pyright error in `tests/test_codefirst_host_contracts.py`.
A negative test passed integer `5` to a parameter statically typed
`str | None`, triggering `reportArgumentType`.

This fix retains all invalid-input assertions and uses `typing.cast(str, 5)`
exclusively at the negative-test call site. The actual runtime value
is still integer `5`, so the validator must still raise `ValueError`.
The legacy test is preserved byte-for-byte in `tests/archive/`.

The executable MCP finalization and security policies remain unchanged;
the version and release-coupled assertions and deployment contract advance
together to `16.3.25.5.115.21.14-code-first-runtime-documentation-convergence`.

## Local verification before push

- Python `compileall` targeted on changed modules and test: PASS.
- `tools/docs_truth_audit.py --root . --json`: `ok=true`.
- Targeted Python tests: 36 PASS in the primary selection, plus 19 PASS in
  the bootstrap-focused selection (overlapping test selection, not 55 unique).
- Pyright CLI itself is not available in the local container. Definitive
  `pyright-active-tree-audit` evidence must come from Actions.
- Existing unrelated `reportUnsupportedDunderAll` warning from `_core.py`
  was not modified in this narrowly scoped regression fix.

## Release gates

Do not merge on this document alone. Require final-SHA GitHub Actions
`pyright-active-tree-audit`, `release-hardening`, persistent-runtime E2E,
package cleanroom, Windows/PowerShell and live ChatGPT MCP acceptance
where needed. The report states verification evidence, not runtime authority.
