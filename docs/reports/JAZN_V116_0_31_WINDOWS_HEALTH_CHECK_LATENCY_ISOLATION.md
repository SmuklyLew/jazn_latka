# Jaźń v16.3.25.5.116.0.31 — Windows health-check timing gate

## Observed failure (PR #374)
Workflow [powershell-terminal-regressions run 38800152941](https://github.com/SmuklyLew/jazn_latka/actions/runs/38800152941), full deterministic suite on Windows Python 3.12.9: `test_isolated_health_check_is_fast_valid_and_has_no_semantic_write` took 13.810194 s, although its original assertion requires **strictly less than 5 s**. Overall results: 2578 passed, 14 skipped, 1 failed. Compile, GUI tests, targeted failure surface and clean-checkout guard passed.

## Hypothesis, not an asserted fact
The health check is at 97% of a process that already ran thousands of tests. A wall-clock SLA at the end of the entire process may be affected by earlier Python/plugin/process resource accumulation and shared GitHub Windows runner contention. The logs do not prove which cause dominates.

## Patch to isolate measurement without reducing coverage
- Run the **unchanged production-path test and unchanged 5.0-second assertion** as an independent pytest invocation in a fresh Python process on the same Windows runner, after compile and targeted regression tests.
- In the subsequent full deterministic suite, use pytest's `--deselect` to exclude **only the already-executed latency node ID**, while retaining all other atomicity and regression tests.
- No production runtime optimization, timeout increase, xfail, skip marker, or disabling of source/truth/persistence checks.
- The isolated step remains an ordinary required workflow step. Any latency, integrity, truth, or semantic-write assertion failure in that step fails the workflow.

## Falsifiable acceptance
1. Isolated latency test passes on Windows; 5.0 s bound remains unchanged.
2. Full deterministic suite (other cases preserved) passes.
3. Final HEAD pyright, manifest sync, release-hardening, MCP, persistent E2E and package cleanroom checks are green.
4. If isolated latency fails too, diagnose per-stage telemetry and optimize the canonical runtime, not the assertion.
5. This CI change is not evidence of real ChatGPT MCP connectivity or private MEMORY activation.

References: [pytest deselection](https://docs.pytest.org/en/stable/example/pythoncollection.html), [pytest node IDs](https://docs.pytest.org/en/stable/example/markers.html).
