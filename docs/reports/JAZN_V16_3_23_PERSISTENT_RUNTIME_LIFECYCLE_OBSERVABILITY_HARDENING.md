# Jaźń v16.3.23 — Persistent Runtime Lifecycle + Host Pre-Response Gate

## Status

- Distribution/package version: `16.3.23`
- Release name: `persistent-runtime-lifecycle-observability-hardening`
- Full release: `16.3.23-persistent-runtime-lifecycle-observability-hardening`
- Base branch: `master`
- Base SHA: `47a49d36af3c9f0bebc03b389c7e3e50e293bff7`
- Working branch: `upgrade/v16.3.23-persistent-runtime-lifecycle-observability`
- Pull request: `#181`
- Code validation SHA before this report: `de59c4e982c762d930e672a1702104bcb6d40558`
- Merge to `master`: **not performed by this hardening session**

This report records the v16.3.23 engineering acceptance evidence. GitHub CI is the authoritative cross-platform proof for this branch; the repository/package itself is not evidence that a user Jaźń runtime is currently active.

## Implemented contract

v16.3.23 hardens the host/runtime boundary around the resolved active runtime and adds explicit lifecycle/transport observability:

1. A deterministic host pre-response gate runs before conversational visible output.
2. Presentation/finalization is fail-closed and only accepts the intended source classes: `runtime_exact`, `runtime_finalized`, or `host_diagnostic` according to the active contract.
3. Host-routing bypass attempts are detectable through explicit telemetry instead of being silently presented as runtime output.
4. Lifecycle control converges on the resolved active **subject root B**, while retaining the requested/configured root diagnostically.
5. Persistent daemon reuse/start and verified one-shot transport are observable as distinct transport outcomes.
6. An explicit persistent-runtime ensure failure cannot silently downgrade to an unverified one-shot path.
7. Two-turn persistent regression coverage exercises the `A -> B -> B` subject-root/lifecycle path.
8. Active-memory recall adds a truth-boundary observability record correlated with runtime turn ID and trace ID.

## Defect loop closed during PR hardening

### Pyright: optional metadata access

`latka_jazn/memory/memory_recall_contract.py` previously repeated `.get()` on a value that Pyright could still regard as optional. The metadata value is now read once, narrowed with `isinstance(..., dict)`, and only then used as a dictionary. Final Ubuntu release-hardening passes both the main static type audit and the regression/pack-generator static type audit.

### Windows rest-cycle synchronization

The Windows regression `test_user_activity_interrupts_slow_rest_generation_without_blocking_chat_path` used a one-second `Event.wait()` only as a thread-entry synchronization bound. That setup bound was raised to five seconds to tolerate runner scheduling variance. The actual chat-path latency assertion remains unchanged (`< 0.25 s`), so the product latency requirement was not weakened. Final Windows targeted release-hardening passes.

### `main.py:main` code-health hotspot

The code-health guard reported `main.py:main` at `1156` lines against a `1151`-line budget. The daemon-turn fallback block was extracted into `_handle_failed_daemon_turn_transport(...)`; the measured post-refactor size was `1146` lines. The budget was not raised.

### `JaznEngine.build_cognitive_frame` code-health hotspot

The deterministic suite initially reported:

- `1 failed, 1184 passed, 2 skipped, 1 warning`;
- sole failure: `JaznEngine.build_cognitive_frame` at `496` lines against a `489`-line budget.

The memory-use-gate / memory-context / recall-contract / recall-observability stage was extracted into `_build_turn_memory_recall_evidence(...)`. Execution order and stage accounting were preserved. The budget was not raised. On final code SHA `de59c4e982c762d930e672a1702104bcb6d40558`, the full deterministic suite and code-health guard pass.

## Fail-closed / negative-path coverage

The v16.3.23 validation matrix covers the expected negative and continuity paths, including:

- requested root A resolving to subject root B and subsequent B reuse;
- root transition / mismatch handling (including A/B/C-style negative cases);
- wrong daemon PID / endpoint identity;
- stale heartbeat or non-live daemon state;
- package integrity verification against subject root B;
- source provenance verification against subject root B;
- invalid/mismatched active-root marker;
- wrong control token / unauthorized loopback access;
- explicit ensure failure remaining fail-closed rather than silently downgrading transport;
- timeout, pending-host-continuation, worker replacement, and next-turn recovery paths;
- presentation/finalization rejection when the runtime evidence is not acceptable.

## Validation evidence

### Focused implementation checkpoint

Recorded before PR-wide CI:

- active-memory recall E2E + host gate: `31 passed`;
- lifecycle transport + MCP/finalization/timeout/provenance: `60 passed`;
- living-memory gateway + runtime-session continuity/status: `18 passed`;
- combined focused checkpoint: `109 passed`;
- `py_compile`: PASS;
- `git diff --check`: PASS;
- `git diff --cached --check`: PASS.

### Final code SHA: `de59c4e982c762d930e672a1702104bcb6d40558`

#### `persistent-runtime-e2e` — run `33201049284`

**Ubuntu (`98950303933`) — PASS**

- compile runtime/gate/regression paths: PASS;
- v16.3.23 host gate and persistent lifecycle E2E: PASS;
- daemon identity/security/atomicity/timeout matrix: PASS;
- presentation/finalization fail-closed matrix: PASS;
- clean checkout guard: PASS.

**Windows (`98950303769`) — PASS**

- compile runtime/gate/regression paths: PASS;
- v16.3.23 host gate and persistent lifecycle E2E: PASS;
- daemon identity/security/atomicity/timeout matrix: PASS;
- presentation/finalization fail-closed matrix: PASS;
- clean checkout guard: PASS.

#### `release-hardening` — run `33201049220`

**Manifest synchronization (`98950336439`) — PASS**

- canonical release metadata synchronization: PASS;
- synchronization idempotency: PASS;
- synchronized PR metadata artifact: produced;
- commit-on-master step: skipped as expected for an open PR.

**Ubuntu verification (`98950400069`) — PASS**

- compile all active Python: PASS;
- Pyright static type audit: PASS;
- static type regression + pack-generator contracts: PASS;
- independent semantic route audit: PASS;
- cognitive architecture audit: PASS;
- full deterministic test suite: PASS;
- clean checkout guard: PASS.

The Ubuntu pytest failure artifact step was skipped because the test step succeeded. Therefore this report does not infer a final numerical `passed` count that was not emitted through the retained success artifact; the authoritative fact is the successful deterministic-suite job/step.

**Windows targeted verification (`98950400006`) — PASS**

- targeted Windows runtime/path tests: PASS;
- turn atomicity and timeout regressions: PASS;
- clean checkout guard: PASS.

**Release finalization (`98950880627`) — SKIPPED**

Expected for the open PR; no release-to-master finalization is claimed by this report.

## Release metadata

`latka_jazn/version.py` declares:

- `DISTRIBUTION_VERSION = "16.3.23"`;
- `PACKAGE_VERSION = "16.3.23"`;
- `PACKAGE_RELEASE_NAME = "persistent-runtime-lifecycle-observability-hardening"`.

The release-hardening manifest synchronization and idempotency checks pass on the validated code SHA.

## Truth boundary

- No private user memory is committed by this PR.
- No claim is made that a user runtime is active merely because this branch or package exists.
- This PR does not close the real-private-memory acceptance work tracked separately by Issue `#59`.
- v16.4.0 NLP work is not part of this PR and remains a separate stage/STOP boundary.
- This report does not authorize or perform the merge to `master`.

## Acceptance rule

The code state at `de59c4e982c762d930e672a1702104bcb6d40558` satisfies the v16.3.23 engineering gates listed above. Because adding this report creates a new PR HEAD, **GO to master must only be declared after the normal required workflows also pass on the final report-containing HEAD**.
