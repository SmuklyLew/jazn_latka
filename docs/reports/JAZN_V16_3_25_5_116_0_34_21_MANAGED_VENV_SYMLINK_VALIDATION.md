# Dependency Studio POSIX venv symlink validation — 16.3.25.5.116.0.34.21

## Evidence

[Cleanroom run 39436897992](https://github.com/SmuklyLew/jazn_latka/actions/runs/39436897992) for source .34.20 fails all six consumer jobs. On Linux, canonical offline start installs dependencies and establishes an active trusted daemon; the new poststart marker validator reports `managed_environment.ready=false` because `managed_environment.errors=["python_outside_environment"]`. The recorded interpreter is `<env>/bin/python` and is a POSIX symlink to the base interpreter, which `Path.resolve()` follows outside `<env>`. Windows has a related failure in dependency-empty invocation. This is not evidence that `tzdata` is undeclared: core `pyproject.toml` already declares it.

## Corrected path security contract

`managed_environment_status()` checks the recorded executable's **canonical entry path**, exactly `<resolved_env>/bin/python` (POSIX) or `<resolved_env>/Scripts/python.exe` (Windows), without following the executable symlink. It **does** resolve the parent directory and rejects a redirected `bin` or `Scripts` directory, checks the `pyvenv.cfg` marker exists, verifies the entry is a file and retains all existing managed-root restrictions, Python target/platform/ABI checks, hash-locked wheelhouse manifest and lock hashes, import-smoke and dependency fingerprint checks. This does not grant write permission or relax archive verification.

New tests cover normal POSIX symlink, forged external executable path, redirected parent directory and missing `pyvenv.cfg`; existing target-drift coverage remains. Original test snapshot is preserved in `tests/archive/`.

## Acceptance

Fresh six-platform cleanroom success (Windows/Linux, Python 3.12–3.14) is mandatory, plus full Pyright, deterministic pytest, release-hardening, Windows PowerShell and manifest sync. The actual ChatGPT host/MCP activation and user MEMORY are separate from these CI assertions; no private data are changed.

References: https://docs.python.org/3/library/venv.html ; https://peps.python.org/pep-0405/ ; https://docs.python.org/3/library/pathlib.html .
