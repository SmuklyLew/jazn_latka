# Jaźń v16 full-system convergence — baseline

Date: 2026-08-23

Branch: `upgrade/v16-full-system-convergence`

Base: `origin/master` at `504d282d49c275cf257f708f2e93d5986f262a8e`

Canonical version: `16.0.6-runtime-turn-liveness-ci-hardening`

## Safety checkpoint

- clean source worktree confirmed before edits;
- local checkpoint: `backup/pre-v16-convergence-20260823-1951`;
- the development worktree is separate from the active runtime checkout;
- `memory/`, `workspace_runtime/`, SQLite/WAL/SHM, ZIPs, secrets, logs and private exports remain excluded from Git.

## Runtime truth gate

The legacy marker under `D:\.AI\jazn_latka_master\workspace_runtime` was stale and is not the current host-level marker. The current runtime uses `D:\.AI\workspace_runtime\JAZN_ACTIVE_RUNTIME.json`.

After a permission-gated start, PID `25552` listened on `127.0.0.1:8787`. Direct `/status-lite` returned the same root and PID, `runtime_active_state=active_trusted`, a fresh heartbeat and `runtime_write_ready=true`. The canonical `run.py status --json` probe nevertheless returned `active_degraded` because its first `/ready` request timed out and blocked the subsequent fallback probes. This is a reproducible observability defect and is part of the convergence scope; the report does not promote the inconsistent CLI result to a clean truth-gate pass.

The exact user request was sent through `run.py chat-gpt`. Runtime returned `action=host_diagnostic`; no Jaźń-visible reply was fabricated.

## Baseline validation

- `compileall`: exit `0`;
- semantic route audit: `132/132`, `ok=true`;
- cognitive architecture audit: all `24` checks true, `12/12` dialogue regressions true;
- local Pyright: unavailable; canonical CI uses Pyright `1.1.411`;
- full deterministic pytest on Windows/Python `3.14.4`: `787 passed, 4 skipped, 23 failed`;
- system package smoke: failed during cleanup of an open `rest_cycle.sqlite3` handle (`WinError 32`).

The pytest failures are not recorded as green. The principal classes are:

1. invalid inherited stdin handles in subprocesses (`WinError 6` / `WinError 50`) in this host;
2. POSIX-only `termios` test collected on Windows;
3. SQLite handles surviving temporary-directory cleanup on Python 3.14;
4. SQLite read-only URI attach incompatibility in the sidecar migration path;
5. runtime full-turn memory count mismatch (`2` observed, `3` expected);
6. isolated daemon startup/status readiness timeout on Windows.

## Semantic archaeology

`upgrade/jazn-model-bridge-v2` is 449 commits behind current master and has one unique commit. It is used only as an invariant source. Candidate invariants include bounded model context, explicit memory authorization/use declaration and candidate evaluation before persistence. Its old `host_model_bridge.py` is not a merge candidate.

`fix/epistemic-rest-consolidation-hardening` is 120 commits behind current master and has 22 unique commits. Its useful concepts are the evidence collector, fail-closed claim guard, hash-chained decision ledger, explicit promotion gate and deterministic offline rest path. These will be adapted to current v16 contracts rather than cherry-picked.

The history-only `fix/sqlite-runtime-io-hardening` and already-merged `upgrade/local-first-memory-cloud-v155-full` are excluded from automatic merge; only post-merge semantic differences may be considered.

## Issue #59 / private data

The public GitHub query was not authenticated in this environment. Current repository documentation still marks Issue #59 open and requires real private import, recall, restart, multi-turn and L3-review evidence before closure. Local private-data discovery and acceptance are handled in stage D; no private content or path inventory is written to this report.
