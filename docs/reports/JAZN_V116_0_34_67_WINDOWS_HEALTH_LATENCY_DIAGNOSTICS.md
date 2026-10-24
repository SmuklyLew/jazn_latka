# .67: Windows isolated health-check latency — diagnostic checkpoint

**Scope:** failing required Windows PowerShell gate on PR #414; no exception, no
timeout increase, no xfail, no removal of test coverage, no release acceptance.

## Confirmed evidence

- [Windows PowerShell run 40064230973](https://github.com/SmuklyLew/jazn_latka/actions/runs/40064230973),
  job `120783975667`: strict `test_isolated_health_check_is_fast_valid_and_has_no_semantic_write`
  failed with `duration=5.755362899999909 s` vs required `<5.0 s`.
- [Earlier .65 release-hardening run 40050989918](https://github.com/SmuklyLew/jazn_latka/actions/runs/40050989918):
  Windows targeted originally exceeded the same limit (~5.154 s); job rerun passed.
- The separate fresh-process test gate was previously implemented in
  [v116.0.31 health isolation report](../reports/JAZN_V116_0_31_WINDOWS_HEALTH_CHECK_LATENCY_ISOLATION.md).
  Its repeat failure confirms **process isolation alone has not resolved
  the required performance SLA**. A transient runner delay is a plausible
  cause, not an established root cause.

## New diagnostic evidence collection

The original test is archived byte-for-byte at
`tests/archive/v16.3.25.5.116.0.34.66-before-health-latency-diagnostics/test_turn_atomicity.py`
per AGENTS.codex.md. Its active copy preserves the exact `assert duration < 5.0`
and all final integrity, route, truth and semantic write assertions.
For measured runtime >=3.0 s it emits only wall duration, names and numeric
`turn_telemetry.stages[*].duration_ms` and unchanged semantic-write bool.
There are no prompts, private memory, paths, tokens or stage payloads.
On assertion failure pytest includes this captured stdout in GitHub logs.

The timing diagnostic is a **measurement**, not an optimization. It does not
claim that Python 3.12 or the local daemon is now faster. Do not turn failure
into a success or modify the requirement until diagnostics indicate a
reproducible, source-attributed cause.

## Next actions after GitHub Actions

1. Inspect `ISOLATED_HEALTH_LATENCY_DIAGNOSTICS` on any failing Windows job.
2. Correlate `total_execution_time` vs stage timings; high `startup_status_collection`,
   model-free setup, persistence or audit stages suggest different owners.
3. If no expensive stages explain wall duration, profile uninstrumented gaps
   or Windows runner preemption separately.
4. Implement a focused production optimization with a regression and unchanged
   safety/latency gate if reproducible.
5. Keep P1–P3 migration incomplete and P5 Avast `IDP.Generic` security HOLD;
   offline + independent external SYSTEM remain NOT RUN.

References: [pytest flaky test guidance](https://docs.pytest.org/en/latest/explanation/flaky.html),
[PyInstaller bootloader and false positives](https://www.pyinstaller.org/en/stable/bootloader-building.html).
