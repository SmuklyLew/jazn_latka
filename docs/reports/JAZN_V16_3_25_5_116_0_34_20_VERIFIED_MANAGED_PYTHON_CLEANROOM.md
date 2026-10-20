# Cleanroom managed-interpreter validation — v16.3.25.5.116.0.34.20

## New evidence

The first workflow-order correction from version .34.19 still failed all 6 cleanrooms, as shown by [run 39434908343](https://github.com/SmuklyLew/jazn_latka/actions/runs/39434908343). Unlike the previous run, `run.py start` succeeded and on Linux the daemon became live. However `run.py doctor` invoked again from the original dependency-empty interpreter still reported `dependency_source=missing` with `tzdata` and `packaging` absent, even though a managed runtime was already operating. Windows again raised `ZoneInfoNotFoundError("Europe/Warsaw")`.

## Minimal safe change

The consumer cleanroom now keeps the first `BARE_PYTHON run.py status` (inactive/no dependency install) and `BARE_PYTHON run.py start` (authorized offline install + real daemon). Subsequent diagnostic/lifecycle commands run in an **independently verified managed interpreter**. A tiny Python dispatcher, created only inside the temporary GitHub runner, calls `dependency_activation_status(root)` and requires `required_ready`, profile coverage, valid `managed_environment.ready` and an existing managed Python path before invoking `run.py`. Any missing or tampered marker fails loudly with a structured `verified_managed_python_not_ready` report (exit 78). This does NOT bypass package hash locks or re-enable dependency installation during diagnostics; it keeps `main.py` as sole CLI control plane.

The original dependency-empty preflight and missing sidecar negative tests remain, along with daemon status/idempotence/stop assertions. New test: `test_package_distribution_cleanroom_verified_managed_python.py`. Altered existing tests have immutable source snapshots.

## Limits

This change proves the correct consuming interpreter *if* the canonical marker verifies. If it fails, inspect `managed_environment.errors` in job logs and repair the actual marker/provenance problem; never silently pick an arbitrary Python executable. Real ChatGPT host exec/MCP exposure remains an independent acceptance gate.

Sources: https://docs.python.org/3/library/venv.html ; https://docs.python.org/3/library/zoneinfo.html ; https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs .
