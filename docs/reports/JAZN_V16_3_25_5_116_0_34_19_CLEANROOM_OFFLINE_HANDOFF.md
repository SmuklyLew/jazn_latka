# Jaźń cleanroom offline handoff fix — 16.3.25.5.116.0.34.19

## Evidence

[Package cleanroom run 39433164530](https://github.com/SmuklyLew/jazn_latka/actions/runs/39433164530) failed in **all 6** cleanroom jobs (Windows/Linux, CPython 3.12/3.13/3.14), whereas the native dependency artifact builds and cross-target lock replays succeeded. The failing step ran `run.py doctor --json` using a deliberately dependency-empty interpreter *before* any authorized activation. On Windows this could import `memory_intent_contract.py` and execute `ZoneInfo("Europe/Warsaw")` with no installed `tzdata`, ending in `ZoneInfoNotFoundError`.

This is a **test-order contract regression**, following the intentional change to `main.py`: read-only diagnostic commands no longer silently install missing dependencies. The canonical `pyproject.toml` already declares `tzdata>=2024.1`; Windows needs the IANA database available through `tzdata`, as documented by the [Python zoneinfo docs](https://docs.python.org/3/library/zoneinfo.html). Do not implement a fake timezone or weaken dependency verification.

## Repair

The package cleanroom now checks `status` with no daemon, then exercises `run.py start` to verify authorized offline dependency preparation and real daemon creation. Only *after* the verified offline handoff does it run `run.py doctor` and `host-diagnose` through the same `BARE_PYTHON` entrypoint. Both the `doctor` check and the existing daemon status gates then require live readiness, while the original prestart status remains a separate negative test. Assertions for integrity, `start` idempotence, `stop`, sidecar-removal failure and core operational/memory boundaries are preserved.

Revised deterministic tests: `tests/test_package_distribution_cleanroom_prestart_contract.py` and `tests/test_package_distribution_cleanroom_doctor_semantics.py`. Immutable original snapshots under `tests/archive/`. Do **not** present structural tests as proof of an actual cleanroom run.

## Remaining

- Require new six-platform cleanroom success, full `release-hardening`, Windows PowerShell, Pyright and Test Studio catalog sync on the latest source revision.
- The auto-generated manifest/provenance follow-up commit can use `[skip ci]`; inspect the PR merge checks and actual provenance instead of borrowing earlier SHA checks.
- Real ChatGPT host activation and MEMORY data contents remain untested. No private MEMORY, SQLite or user data are changed.

Upstream references: https://docs.python.org/3/library/zoneinfo.html ; https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs .
