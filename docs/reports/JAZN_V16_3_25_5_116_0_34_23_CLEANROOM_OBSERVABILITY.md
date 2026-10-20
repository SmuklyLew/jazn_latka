# PR #392 cleanroom observability convergence — 16.3.25.5.116.0.34.23

## Ground truth (2026-10-20)

- `release-hardening` PR run 39443429933 Ubuntu: 2756 passed, 14 skipped, 1 failed. The only failure is `test_package_distribution_cleanroom_activation_observability.py::test_cleanroom_prints_each_activation_payload_before_asserting`.
- `powershell-terminal-regressions` PR run 39443429970 Windows: same test failure (2716 passed, 19 skipped, 1 deselected). Windows daemon teardown and dedicated isolated health check completed without triggering this workflow's failing assertion.
- `package-distribution-cleanroom` PR run 39443430151: 6 of 6 Linux/Windows Python 3.12-3.14 consumer environments passed.
- Source revision `3a4846b32c9` changed the bare interpreter pre-activation operation from full `status` to stdlib-safe `host-preflight`, retaining JSON output and exit-code checks. The workflow's observability test remained written for `status.json/status_rc` and had no corresponding `preflight.json/preflight_rc` expectation.

## Repair

The existing deterministic contract test now requires `preflight.json` to be printed and its exit code recorded before validation. All other outputs remain required: start, doctor, status-after-start, start-again, and stop, with their own exit-code checks. A second regression ensures host-preflight occurs before offline activation, validates gate evidence, and explicitly rejects running `doctor` or full `status` on the deliberately dependency-empty interpreter before `start`. The exact old test is preserved unchanged in `tests/archive/test_package_distribution_cleanroom_activation_observability__source_v16_3_25_5_116_0_34_22.py`.

The working cleanroom workflow is deliberately **not** rewritten to satisfy a stale assertion: the existing preflight boundary avoids importing `zoneinfo` before verified `tzdata` activation on Windows. No security or runtime readiness gate has been removed.

## Required acceptance

New source commit must pass full pytest on Ubuntu/Windows, Pyright, cleanroom six-platform matrix, release-hardening, and the final canonical metadata synchronization. Verify the PR merge or head SHA required checks; the metadata commit with `[skip ci]` cannot substitute for required checks. Real ChatGPT MCP tool exposure/finalization still requires separate host-side acceptance. No MEMORY package contents or live database were modified.

Upstream:
- https://docs.python.org/3/library/zoneinfo.html
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
