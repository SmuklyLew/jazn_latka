# Jaźń v16.1.0 — epistemic truth and model-free rest

Date: 2026-08-23

Version: `16.1.0-epistemic-offline-rest-consolidation`

## Delivered contract

- the evidence collector keeps verified rest reports, runtime event IDs,
  memory source IDs, external source IDs, model inference, hypotheses,
  synthetic dream artifacts and fiction as separate evidence classes;
- numeric claims are derived from bounded identifiers; an unsupported count,
  daemon presence or model confidence cannot promote a claim;
- strong visible claims about dreams, background work and runtime actions are
  rejected before persistence unless their required machine evidence exists;
- direct runtime replies and ChatGPT-host-finalized replies cross the same
  epistemic guard;
- decisions are recorded in a bounded, append-only SQLite hash chain under the
  canonical runtime workspace; prompt text, raw content, secrets and reasoning
  traces are excluded;
- synthetic output can never promote itself or auto-promote to L3;
- a usable source anchor needs an eligible truth status, stable source locator
  and valid integrity hash; conflicting content under one source identity is
  routed to review;
- deterministic offline consolidation runs immediately after replay and does
  not require Dream or any model;
- lack of Dream completes as `offline_consolidation_only`, without converting
  an ordinary dialogue or a useful rest pass into failure.

## Regression coverage

The focused suite covers unsupported dream claims, counts without IDs, a live
daemon without recorded work, high-confidence inference, synthetic text used as
fact, decision-ledger tampering and boundedness, no source anchor, automatic L3,
source conflicts, inferred-only L2, no Dream and compatibility with existing
rest, host-finalization and ordinary dialogue paths.

## Verification

- focused epistemic, rest, host-finalization and compatibility suite:
  `38 passed`; post-refactor code-health/epistemic gate: `16 passed`;
- Pyright `1.1.411`: `0 errors, 0 warnings`;
- compileall: passed;
- semantic route audit: `132/132`, `ok=true`;
- cognitive architecture audit: all `24` checks true, including `12/12`
  dialogue regressions;
- system package smoke: `14` required checks passed, `ok=true`; the stale
  source-manifest mismatch is optional for dirty development staging;
- full deterministic Windows/Python 3.12 suite after the final refactor:
  `825 passed, 5 skipped, 9 failed`.

The first full run found one new code-health failure because `process_turn` grew
beyond its 713-line budget. The epistemic boundary and staged ledger append were
extracted into a dedicated method; the focused code-health suite and the second
full run both confirm that regression is fixed.

The nine remaining failures are the pre-existing Windows/Python baseline:
one POSIX-only terminal test, four SQLite snapshot handle-cleanup failures, one
transactional-memory count assertion, one isolated wake-state readiness test,
one Windows read-only sidecar URI failure and one legacy repack SQLite handle
cleanup failure. They remain explicit work items for stages C, F and G rather
than being hidden or waived here.

No private memory, SQLite database, runtime workspace or generated archive is
part of this release checkpoint.
