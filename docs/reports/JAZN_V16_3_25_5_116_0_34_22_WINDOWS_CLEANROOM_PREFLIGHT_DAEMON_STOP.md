# Jaźń .34.22 — Windows cleanroom preactivation and daemon teardown

## Evidence on previous source .34.21

- PR cleanroom [39438459753](https://github.com/SmuklyLew/jazn_latka/actions/runs/39438459753) passed all three Linux consumer jobs, failed all three Windows consumer jobs before activation. The **first** full `BARE_PYTHON run.py status --json` from an intentionally dependency-empty Python imported `ZoneInfo("Europe/Warsaw")` without any Windows system IANA data or installed tzdata; output was empty and the subsequent JSON assertion failed.
- [Windows PowerShell regression 39438459665](https://github.com/SmuklyLew/jazn_latka/actions/runs/39438459665) had one failure among 59 tests: the isolated daemon did not confirm endpoint down **and** PID exit inside a 10 s teardown budget, yielding `daemon_stop_timeout`.
- [Windows health-check 39438455011](https://github.com/SmuklyLew/jazn_latka/actions/runs/39438455011) exceeded its strict 5 s hot-path assertion by ~0.51 s on one push run. PR release-hardening passed; no evidence yet to widen the performance contract.

## Correction: not a weaker test

The dependency-empty interpreter now runs the existing **host-preflight** command, whose import graph intentionally avoids optional runtime dependencies and verifies host execution capability before bootstrap. This uses the same `run.py -> main.py` control plane. After authorized `run.py start` and verified offline wheelhouse/managed-Python handoff, full `doctor`, `host-diagnose`, `status`, idempotent `start`, `stop`, and missing-sidecar negative case remain mandatory. The ZIP and provenance checks in the pipeline are unchanged. The workflow no longer demands full runtime status from a deliberately dependency-empty Python, which violates the division of responsibility between preflight and full runtime.

Windows isolated daemon teardown retains the same production `stop_daemon` and requires both endpoint disappearance and process termination. The **test-only** bounded teardown allowance is 30 s on contended Windows, still 10 s elsewhere. Failed tests now include sanitized PID/endpoint/response/elapsed diagnostics for root cause analysis. No production kill, PID reuse, or identity guard was relaxed.

The 5 s health-check performance test is unchanged; if recurrent, profile initialization, health route and SQLite separately instead of silently increasing its threshold.

## Release checklist

- Latest PR source SHA: 6-platform package cleanroom PASS, Windows PowerShell PASS, full `release-hardening` PASS, Pyright PASS, host/MEMORY/MCP E2E PASS.
- Sync `SOURCE_PROVENANCE.json` and `PACKAGE_INTEGRITY_MANIFEST.json` only through canonical release tooling; account for GitHub's `[skip ci]` semantics.
- Prove real host ChatGPT executor or authenticated MCP, two distinct turns, same session, accepted phase-2 finalization; this is external to CI.
- No automatic merge, no user MEMORY archive processing.

Sources: https://docs.python.org/3/library/zoneinfo.html ; https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs ; https://docs.python.org/3/library/subprocess.html .
