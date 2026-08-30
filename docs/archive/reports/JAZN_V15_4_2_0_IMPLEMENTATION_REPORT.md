# Jaźń v15.4.2.0 — Rest / Replay / Dream Continuity implementation report

## Summary

The implementation adds a bounded, daemon-owned process for auditable activity between user turns. The process remains fail-soft for ordinary dialogue and fail-closed for factual-memory claims.

## New modules

- `latka_jazn/core/rest_cycle_controller.py` — idle scheduler and phase orchestration.
- `latka_jazn/memory/rest_contracts.py` — truth/status contracts.
- `latka_jazn/memory/rest_cycle_store.py` — transactional SQLite ledger.
- `latka_jazn/memory/rest_replay.py` — read-only source-grounded replay selector.
- `latka_jazn/memory/dream_sandbox.py` — local-only, tool-less synthetic scene generator.
- `latka_jazn/memory/rest_reflection.py` — deterministic independent first-pass evaluator.
- `latka_jazn/memory/rest_consolidation.py` — shadow/L2-only consolidation gate.
- `latka_jazn/memory/rest_wake_report.py` — hash-verified report and read-only loader.

## Existing modules extended

- `JaznConfig` gets explicit rest controls and a dedicated rest DB path.
- `JaznDaemonServer` owns the controller, reports its state and resets it on accepted user activity.
- `WakeStateRuntimeBridge` carries a bounded rest report independently of the ordinary wake continuity claim.
- `scientific_basis.py` records primary research relevant to memory/reflection/simulation safety.
- `cognitive_architecture_audit.py` verifies presence of rest components and core invariants.
- version advances to `v15.4.2.0-rest-replay-dream-continuity`.

## Truth boundary

The runtime may later say that it *executed recorded internal rest cycles* only when a valid report proves them. It may not infer a biological dream or subjective experience from that record. A scene is always synthetic. The normal wake-state remains the authority for cross-session continuity of memory; a rest report does not grant `continuity_claim_allowed` by itself.

## Safe rollout

Shadow mode is intentionally the default. It provides replay, local generation, evaluation, decisions and wake reports while making no L2 memory write. Non-shadow mode is implemented for controlled testing but is constrained to `INFERRED` short-term candidates with independent real-source anchors and `requires_review` tags. L3 remains blocked.

## Validation strategy

The dedicated tests cover all seven phases (0–6), including an accelerated deterministic eight-hour scenario, report tampering, SQLite constraints, missing source/model behaviour, L2-only materialization and daemon fail-soft initialization. Existing daemon/wake/continuity tests are also part of the release gate.

- Windows release-hardening targetuje również scheduler/rest store/wake continuity v15.4.2.0.
