# Jaźń v16.3.25.5.108 — engine decomposition turn diagnostics convergence

**Date:** 2026-10-06  
**Baseline:** `master @ 712a25db94c634ea47fbf265c0d907608a668f00`  
**Baseline release:** `16.3.25.5.107-persistent-remote-runtime-operations-convergence`  
**Branch:** `upgrade/v16.3.25.5.108-engine-decomposition-turn-diagnostics-convergence`  
**Target:** `16.3.25.5.108-engine-decomposition-turn-diagnostics-convergence`

## 1. Purpose

v108 is the safety harness for later `JaznEngine` decomposition. It does not
replace the canonical turn runtime yet. It makes the current turn path
auditable enough that later extraction can prove parity or identify the exact
point of divergence.

The release establishes:

```text
one TurnExecutionContext
→ one TurnDiagnosticTrace
→ typed route/handler/validation/fallback evidence
→ blind-route detection
→ static route-graph CI gate
→ explicit EngineServices seams
```

## 2. Implemented modules

### `latka_jazn/core/turn_diagnostics.py`

Adds:

- `TurnStage`;
- `FailureKind`;
- `FallbackKind`;
- `DiagnosticSeverity`;
- `DiagnosticEvent`;
- `FallbackDecision`;
- `BlindRouteFinding`;
- `TurnDiagnosticTrace`.

The trace has:

- monotonic event sequence;
- stable diagnostic id `JAZN-TURN-...`;
- route/handler binding;
- stable failure signature;
- typed fallback lineage;
- fallback history;
- immutable final outcome;
- privacy boundary and bounded attribute sanitization.

### `latka_jazn/core/turn_execution.py`

`TurnExecutionContext` is the diagnostic root owner. This avoids creating a
parallel global logger or a second turn owner.

The context now provides:

- diagnostic event recording;
- route binding;
- fallback/failure recording;
- blind-route findings;
- final diagnostic settlement;
- diagnostic snapshot embedded in existing turn telemetry.

### `latka_jazn/core/route_handler_dispatcher.py`

Previously an unresolved handler silently selected `FallbackHandler`, while a
handler exception returned a fallback with only a generic `handler_error`.

v108 preserves visible fallback behavior but adds explicit evidence:

```text
ROUTE_HANDLER_UNRESOLVED
HANDLER_EXCEPTION
```

with origin stage/component and from/to route lineage.

### `latka_jazn/core/blind_route_detector.py`

Consumes already-produced runtime evidence. It does not classify natural
language.

Checks include:

- missing intent/route/handler;
- degraded dispatch;
- required components missing;
- validation rejection without reason;
- anonymous fallback.

### `latka_jazn/core/route_graph_contract.py`

Static graph audit checks:

```text
DialogueIntentClassifier literal intents
→ RouteRegistry
→ RouteHandlerDispatcher
→ required component ownership
```

Release fails when the graph contains unexplained unresolved routes or active
anonymous fallback registration.

### `latka_jazn/tools/route_graph_audit.py`

Provides the deterministic CI/operator command:

```bash
python -X utf8 -m latka_jazn.tools.route_graph_audit --root . --json
```

### `latka_jazn/core/engine_services.py`

Introduces extraction seams only. It wraps existing collaborators and does not
take lifecycle/session/finalization ownership in v108.

## 3. Existing runtime integration

### Intent / route

`JaznEngine.process_turn` records classifier output and binds selected
intent/route/handler to the same turn-root diagnostic trace.

### Handler

Dispatcher outcome and typed dispatcher fallback are recorded without changing
the existing handler response contract.

### Validation / repair

Initial and final `RuntimeAnswerValidator` outcomes are separate events.
Repair does not erase attempt 0 evidence.

### Model / external capability

Model retry is visible as a separate attempt. Legacy
`cannot_answer_directly` is additionally projected to typed diagnostics:

- `EXTERNAL_CAPABILITY_REQUIRED` when host model is required;
- `TERMINAL_DIAGNOSTIC` when the turn cannot safely continue.

Legacy `fallback_classification` remains available because existing
truth/finalization code still depends on it.

### Finalization / persistence

`JaznRuntimeSession` adds truth-gate, integrity-consensus, persistence and
settlement events to the same trace.

Final outcomes distinguish:

```text
completed
completed_persistence_degraded
awaiting_host_finalization
rejected
failed
```

Phase-1 `awaiting_host_finalization` intentionally remains an intermediate
outcome. Extraction of phase-2 finalization from full `JaznEngine` is a v109
milestone.

## 4. Privacy boundary

The diagnostic contract must not become a second private memory.

Default diagnostics do not intentionally collect:

- raw user message;
- full prompt;
- private memory excerpt;
- journal content;
- tokens/secrets/auth headers.

Sensitive attribute keys are redacted. Cancellation diagnostics record only
that a human-readable reason was present, not the raw reason.

Telemetry remains technical evidence, not autobiographical MEMORY.

## 5. Tests added

```text
tests/test_turn_diagnostics_contract.py
tests/test_blind_route_and_route_graph_audit.py
tests/test_route_dispatcher_fallback_diagnostics.py
tests/test_engine_service_decomposition_seams.py
tests/test_turn_route_characterization.py
```

The active suite also migrates the v107 release-coupled test filenames to
stable-purpose names:

```text
tests/test_memory_manifest_producer_gate.py
tests/test_persistent_remote_runtime_operations.py
```

Exact pre-rename v107 sources are preserved under
`tests/archive/v16.3.25.5.107-stable-purpose-name-migration/`, in accordance
with test-governance policy.

Coverage includes:

- monotonic event sequence;
- privacy redaction;
- typed fallback lineage/history;
- immutable final outcome;
- one diagnostic root per execution context;
- cancellation classification;
- route graph closure;
- missing required component;
- anonymous fallback detection;
- unresolved handler fallback;
- handler exception fallback;
- extraction seams;
- representative current route characterization.

## 6. CI changes

### release-hardening

Adds explicit:

```text
Turn route graph and no-silent-fallback audit
```

after the existing semantic route audit.

### persistent-runtime-e2e

Linux and Windows both run the new v108 diagnostic regression set and route
graph audit.

The existing full deterministic suite, Pyright, compileall, package cleanroom
and release metadata gates remain mandatory.

## 7. Deliberately deferred to v109+

v108 does **not** claim the `JaznEngine` rewrite is complete.

Still intentionally open:

- `JaznEngine.__init__` remains side-effectful;
- procedural seeding still belongs to engine construction;
- project indexing can still write during construction;
- phase-2 host finalization still constructs a full `JaznEngine`;
- `conversation.py` remains a large legacy dialogue surface;
- `ConversationRunner` and `TurnStateMachine` are not canonical yet.

These are sequenced as:

```text
v109  construction/lifecycle + FinalizationService
v110  TurnOrchestrator + internal pipeline decomposition
v111  ConversationRunner + TurnStateMachine + legacy dialogue cutover
```

## 8. Truth boundary

A green v108 proves repository implementation/test properties only.

It does not prove:

- that a particular ChatGPT message has the Jaźń app callable;
- that the public MCP deployment is currently reachable;
- that autobiographical MEMORY is attached;
- that a future v109-v111 refactor already exists.

No visible message may be attributed to Jaźń without the existing accepted
finalization / `display_exact` contract.

## 9. Merge gate

The branch is not merge-ready until the same final PR HEAD has:

```text
compileall                                      PASS
Pyright                                         PASS
route_graph_audit                               PASS
full deterministic pytest                       PASS
persistent-runtime-e2e Linux                    PASS
persistent-runtime-e2e Windows                  PASS
release-hardening                               PASS
package-distribution/cleanroom                  PASS where triggered
canonical release metadata sync                 PASS
no unresolved review blocker                    PASS
```

Merge still requires explicit user approval.
