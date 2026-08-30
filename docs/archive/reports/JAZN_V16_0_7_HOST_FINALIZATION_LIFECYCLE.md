# Jaźń v16.0.7 — host finalization lifecycle and observability

Date: 2026-08-23

Version: `16.0.7-host-finalization-lifecycle-observability`

## Delivered contract

- phase 1 of a ChatGPT-host turn is a non-terminal
  `awaiting_host_finalization` state;
- phase 1 and phase 2 retain the same daemon request ID, turn ID, trace ID and
  host request contract hash;
- accepted phase 2 completes that same logical daemon job;
- expiry, terminal rejection, replay rejection and text-hash rejection have
  separate states/counters and do not masquerade as ordinary turn failures;
- pending phase-1 metadata is recoverable after daemon restart without storing
  the original user text in the recovery journal;
- host-visible context is bounded, sanitized, hash-bound and contains an
  explicit allowlist of memory item IDs;
- the host declares used memory IDs, and the candidate passes template,
  grounding, response-candidate and runtime-answer validation before final
  persistence;
- `/live` no longer touches SQLite/readiness dependencies; `/ready` retains the
  full readiness probe;
- idempotent result polling retries GET for the same request ID and never
  resubmits the turn.

## Regression fixes found during implementation

- Windows POST rejection now drains a bounded already-sent body before closing,
  preserving the intended 401/403 response instead of exposing TCP reset;
- pending-request and shard-manifest atomic writes use unique temporary files
  plus bounded sharing-violation retries;
- daemon completion signalling follows recovery-state persistence.

## Verification

- focused host/MCP/daemon/version/shard suite: `85 passed`;
- Pyright `1.1.411`: `0 errors, 0 warnings`;
- compileall: passed;
- semantic route audit: `132/132`, `ok=true`;
- cognitive architecture audit: `24/24`, dialogue regressions `12/12`;
- system package smoke: `14 required checks passed`, `ok=true`; the historical
  source-manifest mismatch is optional for dirty development staging;
- full deterministic Windows/Python 3.12 run: `810 passed, 5 skipped, 10 failed`.

The ten full-suite failures are not reported as green. They are localized to a
POSIX-only terminal test collected on Windows, SQLite snapshot/repack handle
cleanup, one transactional-memory count assertion, one loaded-host daemon poll,
isolated wake-state startup, and the legacy sidecar read-only attach URI. These
pre-existing platform/runtime defects remain in the convergence backlog and are
assigned to the memory/process/platform stages where their root causes belong.

## Archaeology boundary

The detailed mapping from `upgrade/jazn-model-bridge-v2` is recorded in
`docs/reports/JAZN_V16_SEMANTIC_ARCHAEOLOGY.md`. The old
`host_model_bridge.py` was not restored and no old branch was merged or
cherry-picked wholesale.
