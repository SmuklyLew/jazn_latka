# Jaźń v16.3.25.5.62 — turn settlement authority convergence

**Status:** implementation candidate / local validation
**Target branch:** `fix/v16.3.25.5.62-turn-settlement-authority-convergence`
**Base:** current `master` v16.3.25.5.61

## Problem

v61 correctly separated daemon liveness, logical turn continuity and accepted-visible readiness, and fixed the case where `phase_result_ready=true` was hidden behind `done=false`. A separate recovery edge remained possible:

```text
daemon job -> failed/runtime_turn_not_accepted
                     |
                     +-> durable/reconstructed phase-1 -> candidate -> consumed
                                                         |
                                                         +-> daemon ACK binding mismatch
```

The exact user text and recovery context could survive while the daemon and durable host-finalization store held different terminal interpretations of the same logical request. A second weakness allowed `phase1_reconstructed_compatibility` to bypass a negative `RuntimeAnswerValidator` result.

## Engineering basis

The update follows established distributed-systems properties rather than adding another ad-hoc exception:

- AWS Transactional Outbox guidance: a durable state change plus external notification is a dual-write problem; the durable record should be authoritative and delivery must be retryable/idempotent.
  https://docs.aws.amazon.com/en_en/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- SQLite atomic-commit documentation: local transactional state should expose all-or-nothing durable transitions even across interruption. Jaźń retains its existing atomic file transitions for the bounded host-request store instead of adding an unrelated second database solely for this fix.
  https://www.sqlite.org/atomiccommit.html
- OpenTelemetry Context: execution-scoped lineage is propagated across process/API boundaries rather than inferred from transport lifetime. Jaźń therefore keeps `request_id`, `turn_id`, `trace_id`, contract hash and user digest immutable across recovery.
  https://opentelemetry.io/docs/specs/otel/context/
  https://opentelemetry.io/docs/concepts/context-propagation/
- Kubernetes readiness vs liveness: a live process is not necessarily ready to serve output. Daemon health remains distinct from accepted-visible-turn readiness.
  https://kubernetes.io/docs/concepts/workloads/pods/probes/

## Design decision

After a phase-1 request is durably persisted with a `daemon_request_id`, the durable host-request record is the **single settlement authority** for that host-finalized turn.

`DaemonChatJob` remains authoritative for execution/supervision before that binding exists. Once the durable binding exists, daemon state becomes a projection that must reconcile the exact same lineage instead of creating a second terminal truth.

Recovery is intentionally bounded:

- only `runtime_turn_not_accepted` may adopt a later matching durable host settlement;
- worker/process/SQLite/timeouts and unrelated failures remain terminal and cannot be rewritten by host recovery;
- adoption requires one unambiguous durable record with matching daemon request id and user-text digest;
- existing non-empty daemon binding fields must not conflict with the durable record;
- a consumed durable record may settle the matching recoverable daemon job as completed;
- pending/claimed durable records restore `awaiting_host_finalization` so a successor turn cannot silently pass them;
- recoverable failed metadata is persisted across daemon restart without persisting plaintext user text;
- ambiguous duplicate bindings fail closed.

## Candidate validation

`phase1_reconstructed_compatibility` is no longer a weaker acceptance path. `RuntimeAnswerValidator` is enforced for both native and reconstructed phase-1 context. Recovery changes transport/context reconstruction only; it does not lower answer-quality/truth gates.

## Outbox/reconciliation observability

A consumed host request records daemon-finalization notification state (`pending`, `pending_retry`, `delivered`, or `not_applicable`). The consumed durable record remains the settlement authority; notification delivery is an idempotent projection/reconciliation step rather than a second authority.

Both canonical CLI phase-2 and private MCP phase-2 keep visible output fail-closed when daemon settlement has not been confirmed. MCP no longer returns `display_exact` merely because local persistence succeeded while lifecycle notification failed.

## Modified runtime surfaces

- `latka_jazn/core/chatgpt_host_pending_store.py`
  - reverse lookup by `daemon_request_id`;
  - unambiguous durable settlement lookup;
  - outbox notification metadata;
  - explicit settlement authority telemetry.
- `latka_jazn/core/turn_settlement.py`
  - canonical settlement policy and lineage validation;
  - bounded recoverable-execution classification.
- `latka_jazn/core/runtime_daemon.py`
  - adoption/reconciliation of matching durable settlement after `runtime_turn_not_accepted`;
  - recoverable failed-job metadata survives restart;
  - successor-turn admission reconciles such predecessors before deciding they are settled.
- `latka_jazn/core/host_response_candidate_guard.py`
  - same RuntimeAnswerValidator enforcement for native and reconstructed contexts.
- `latka_jazn/cli_commands/host.py`
  - records daemon notification delivery state after canonical phase-2.
- `latka_jazn/mcp/tools/jazn_finalize_reply.py`
  - same notification/outbox semantics as CLI;
  - fail-closed visible output if daemon settlement is incomplete.
- `latka_jazn/core/runtime_ownership_contract.py`
  - ownership map now names the durable settlement authority explicitly.

## Regression contract

New v62 tests cover:

1. `failed/runtime_turn_not_accepted -> consumed durable settlement -> completed daemon job`;
2. pending durable recovery becoming an unsettled predecessor that blocks successor admission;
3. non-recoverable worker failure cannot adopt host settlement;
4. reconstructed phase-1 must obey the same negative RuntimeAnswerValidator result;
5. duplicate daemon-request bindings fail closed;
6. recoverable failed job survives daemon restart and rebinds to the same durable settlement.

Existing v61, MCP, v16.0.7 finalization, v44 evidence-binding and turn-authority tests remain required to prevent regression of the earlier convergence work.

## Truth boundary

This change improves software-level transaction ownership, lineage and recovery. It does not claim biological consciousness and does not make host/platform messages that never enter `run.py` retroactively runtime-owned.
