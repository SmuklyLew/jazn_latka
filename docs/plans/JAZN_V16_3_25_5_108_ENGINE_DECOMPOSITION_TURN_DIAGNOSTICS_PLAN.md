# Jaźń v16.3.25.5.108+ — JaznEngine decomposition and no-silent-fallback diagnostics

**Status:** `PROPOSED_IMPLEMENTATION_PLAN`  
**Date:** 2026-10-06  
**Baseline:** `master @ 712a25db94c634ea47fbf265c0d907608a668f00`  
**Baseline release:** `16.3.25.5.107-persistent-remote-runtime-operations-convergence`  
**Initial implementation target:** `16.3.25.5.108-engine-decomposition-turn-diagnostics-convergence`  
**Parent plans:** `CONVERSATION_RUNTIME_CONVERGENCE_PLAN.md`, `CONVERSATION_RUNTIME_TEST_AND_MIGRATION_MATRIX.md`  
**Related plans:** `AFFECT_ENGINE_CONVERGENCE_PLAN.md`, `LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`

> This plan does not create a second runtime, second session owner, second memory
> owner or second finalization path. It decomposes the existing runtime behind
> the current public contracts and makes every fallback/error route auditable.

## 1. Why this plan exists

v107 closed a different class of problems: production remote-MCP operations,
canonical nested readiness evidence, supervisor ownership, liveness/readiness
separation, deployment contracts and producer-side MEMORY exact-set
verification.

Those changes are now on `master`. They are baseline, not remaining v108 work.

The next structural risk is concentrated in the turn engine itself:

- `latka_jazn/core/engine.py` is about 217 KB and owns too many responsibilities;
- its constructor performs stateful initialization and startup writes;
- `latka_jazn/core/conversation.py` remains a large legacy response/routing surface;
- fallback/error information already exists in several places, but no single
  turn-root diagnostic contract identifies every blind route consistently;
- phase-2 host finalization still constructs a full `JaznEngine` only to persist
  an already generated candidate;
- the active Conversation Runtime plan already calls for one
  `ConversationRunner` / `TurnStateMachine`, therefore decomposition must join
  that plan rather than introduce another orchestration owner.

The desired outcome is not “smaller files” by itself. The goal is:

```text
one turn owner
+ one diagnostic root
+ explicit fallback lineage
+ bounded components with typed contracts
+ parity tests before each ownership switch
= a runtime that can say exactly where and why it deviated
```

## 2. Confirmed current-master facts

At the planning baseline:

1. `run.py` remains the thin public launcher and `main.py` remains the central
   control plane.
2. PR #317 is merged; v107 is the current release.
3. Public MCP deployment now requires canonical nested runtime readiness and
   supervisor evidence.
4. MEMORY v3 production now self-verifies the exact-set manifest before
   archive/transport creation.
5. `TurnRouteTrace` already records route-level information.
6. `RouteHandlerDispatcher` already records `handler_error` and uses a visible
   fallback instead of pretending the failed handler succeeded.
7. `RuntimeAnswerValidator`, `FinalResponseContract`,
   `SourceOriginLedger`, runtime provenance and accepted-visible-turn
   finalization already provide useful evidence.
8. These evidence surfaces are not yet one canonical end-to-end diagnostic
   record.
9. `chat_command_contract.py` still instantiates `JaznEngine` for
   `persist_final_visible_reply(...)`.
10. `JaznEngine.__init__` still seeds procedural rules, opens/creates runtime
    services, initializes project indexing and emits startup events.

## 3. Non-negotiable invariants

The implementation must preserve:

- `run.py -> main.py` main-first control-plane ownership;
- one canonical runtime/session/turn owner;
- one input fingerprint -> one logical turn;
- at most one accepted visible final;
- no host-visible Jaźń voice without accepted `display_exact` finalization;
- no replay of an ambiguous user message;
- MEMORY remains separate from SYSTEM and keeps provenance/truth gates;
- model providers remain interchangeable language/tool executors, not identity
  or memory owners;
- affect remains a bounded software-state contract and does not gain biological
  claims through this refactor;
- no new dependency is required for the decomposition;
- no public command is removed until parity/soak evidence exists.

## 4. Target architecture

The existing Conversation Runtime plan remains authoritative for outer
ownership:

```text
run.py
  |
main.py
  |
ConversationRunner          # session + turn owner
  |
TurnOrchestrator            # one logical turn pipeline
  |
  +-- ContextCoordinator
  +-- CognitiveFrameBuilder
  +-- DialogueRouter
  +-- MemoryCoordinator
  +-- AffectCoordinator
  +-- ResponsePipeline
  +-- ValidationPipeline
  +-- RecoveryPolicy
  +-- FinalizationService
  +-- PersistenceCoordinator
  +-- TurnDiagnostics
```

During migration, `JaznEngine` remains the compatibility facade:

```text
existing callers
    |
JaznEngine.process_turn(...)
    |
TurnOrchestrator.process_turn(...)
```

The facade is removed or reduced only after all supported callers use the
canonical runtime service and parity gates pass.

## 5. One canonical turn diagnostic root

Introduce a typed diagnostic contract, for example:

`latka_jazn/core/turn_diagnostics.py`

Suggested types:

```text
TurnStage
FailureKind
FallbackKind
DiagnosticSeverity
DiagnosticEvent
FallbackDecision
BlindRouteFinding
TurnDiagnosticTrace
```

Minimum `TurnDiagnosticTrace` fields:

- `schema_version`;
- `session_id`, `request_id`, `turn_id`, `trace_id`;
- exact-input SHA-256, but no raw private text in telemetry by default;
- ordered `event_seq`;
- `stage`;
- `component`, `module`, `symbol`;
- `selected_intent`, `selected_route`, `selected_handler`;
- classifier confidence/support semantics;
- required components and produced components;
- validator outcome;
- model/tool capability decision;
- fallback/repair lineage;
- finalization state;
- failure code / failure signature where applicable.

Existing `TurnRouteTrace` must initially remain compatible. It becomes a
bounded route projection of `TurnDiagnosticTrace`, not a competing trace root.

## 6. No-silent-fallback contract

No runtime fallback may be represented only as the string `fallback`.

Every fallback must declare:

```text
fallback_kind
origin_stage
origin_component
reason_code
from_route
to_route
recoverable
required_capability (optional)
evidence_refs
attempt/revision
```

Required high-level classes:

### RECOVERABLE_FALLBACK

A safe bounded alternate path exists.

Example:

```text
dedicated handler failed
-> generic dynamic generation is allowed
-> preserve original failure evidence
```

### EXTERNAL_CAPABILITY_REQUIRED

The runtime can continue only after a host/model/tool capability is supplied.

Example:

```text
runtime cannot generate model-guided wording locally
-> request ChatGPT host candidate
-> same turn_id/request_id is resumed
```

### TERMINAL_DIAGNOSTIC

Continuing could fabricate state, lose lineage or violate truth/finalization.

Examples:

- lineage mismatch;
- stale finalization contract;
- duplicate accepted final;
- unverified memory source used for autobiographical claim;
- unknown critical route with no safe fallback.

Critical paths may not downgrade a `TERMINAL_DIAGNOSTIC` to conversational
fallback text.

## 7. Blind-route detection

Add a runtime/post-turn `BlindRouteDetector` and a static repository
`RouteGraphAudit`.

### Runtime blind-route checks

For each ordinary turn verify:

- classifier produced an explicit decision;
- registry resolved the intent;
- selected handler exists;
- selected handler was actually invoked;
- required components have an owner;
- required components were produced or explicitly marked unavailable;
- validator rejection is associated with the exact stage/component;
- every repair increments attempt/revision and records from/to lineage;
- every fallback has a typed reason;
- finalization does not erase the earlier failure path.

Example desired finding:

```text
code=BLIND_ROUTE_REQUIRED_COMPONENT_MISSING
stage=validation
intent=self_state_question
route=self_state
handler=SelfStateHandler
missing_component=operational_state
repair_attempt=1
```

### Static RouteGraphAudit

Build a deterministic graph from:

```text
DialogueIntentClassifier
-> RouteRegistry.HANDLERS
-> RouteHandlerDispatcher handlers
-> required_components_for(...)
-> validator/response requirements
```

CI gate:

```text
unresolved_intents == 0
routes_without_handlers == 0
unreachable_handlers == 0 (except explicit compatibility-only allowlist)
anonymous_fallbacks == 0
required_components_without_owner == 0
duplicate canonical owners == 0
```

## 8. JaznEngine decomposition strategy

Do not rewrite `engine.py` from scratch.

Use add -> shadow/parity -> switch -> soak -> remove legacy.

### Phase A — characterization before extraction

Before moving behavior:

- freeze representative turn fixtures for major route families;
- record route, handler, cognitive-frame projections, provenance,
  validator result, fallback classification and final contract;
- add failure-injection fixtures for handler/model/memory/validator failures;
- establish a code-health baseline for constructor side effects and major method
  sizes.

Exit gate: current behavior is measurable before ownership changes.

### Phase B — EngineServices / dependency composition

Create a composition object, e.g.:

```python
@dataclass(slots=True)
class EngineServices:
    memory: MemoryCoordinator
    cognition: CognitiveFrameBuilder
    routing: DialogueRouter
    affect: AffectCoordinator
    generation: ResponsePipeline
    validation: ValidationPipeline
    recovery: RecoveryPolicy
    finalization: FinalizationService
    persistence: PersistenceCoordinator
    diagnostics: TurnDiagnostics
```

Initially these fields may wrap existing implementations.

The point is to make dependencies explicit and injectable.

### Phase C — remove startup side effects from constructor

Current construction and runtime start are too tightly coupled.

Target lifecycle:

```text
construct
-> initialize/hydrate
-> start
-> process turns
-> close
```

Move out of `JaznEngine.__init__`:

- startup audit/event writes;
- procedural seeding;
- project index build/write;
- operations that mutate persistent state.

The daemon/runtime owner performs lifecycle; the engine facade receives ready
services.

Exit gate: constructing an engine for a unit test has no persistent side effect.

### Phase D — extract ContextCoordinator + CognitiveFrameBuilder

Move context assembly, session/task projection and cognitive-frame construction
behind typed requests/results.

Do not change Memory/Affect semantics in this phase.

The new boundary records diagnostic events:

```text
CONTEXT_START
MEMORY_PROBE
AFFECT_PROJECTION
COGNITIVE_FRAME_READY
```

### Phase E — extract DialogueRouter

Combine current intent/registry/dispatcher ownership behind one interface:

```python
RouteDecision resolve(RouteRequest request)
RouteExecution execute(RouteDecision decision)
```

`DialogueIntentClassifier`, `RouteRegistry` and
`RouteHandlerDispatcher` remain usable internally, but callers no longer
manually stitch them together.

Every decision emits route evidence and an explicit confidence/support meaning.

### Phase F — extract ResponsePipeline

Handlers should increasingly return structured response intent/evidence rather
than long final prose.

Legacy `conversation.py` remains compatibility input during migration, but its
ready-made conversational responses are moved gradually to:

```text
handler/route evidence
-> ResponsePlan
-> runtime/model NLG
```

Deterministic text remains appropriate for protocol diagnostics, safety/truth
boundaries and short machine status responses.

### Phase G — ValidationPipeline + RecoveryPolicy

Unify:

- runtime answer validation;
- required-component validation;
- mismatch/repair synthesis;
- fallback selection;
- provenance validation;
- terminal truth failures.

A failed first candidate and a repaired candidate must appear as separate
attempts in the same trace.

No repair may overwrite the evidence of why attempt 0 failed.

### Phase H — FinalizationService extraction

This is a priority because phase-2 host finalization currently constructs a
full `JaznEngine`.

Create a narrow service that needs only:

- pending-turn store;
- lineage/binding verifier;
- candidate validator;
- final-response contract/envelope builder;
- accepted-visible-turn persistence;
- session/conversation commit;
- diagnostics/audit.

Then change `chat_command_contract.py` to call the service instead of
constructing the full engine.

Exit gate: host finalization has no dependency on NLP, project indexing,
general routing or memory retrieval.

### Phase I — PersistenceCoordinator

Centralize accepted-turn writes and distinguish:

```text
candidate produced
candidate validated
finalization accepted
visible committed
session state committed
memory projection committed (if eligible)
affect committed (only where current affect contract permits)
```

Persistence ordering must preserve the existing accepted-turn/settlement
invariants.

## 9. Legacy conversation.py migration

`conversation.py` should not be deleted in v108.

First classify each branch into:

```text
PROTOCOL_TEXT
SAFETY_TRUTH_TEXT
STRUCTURED_HANDLER_CANDIDATE
MODEL_NLG_CANDIDATE
COMPATIBILITY_ONLY
DEAD/UNREACHABLE
```

Then migrate by route family with parity tests.

The goal is that normal conversation is not selected primarily by large
hard-coded phrase-to-paragraph mappings.

Removal happens only after route reachability and behavioral parity prove that
the replacement owns the same supported cases.

## 10. MEMORY and Affect scope

This plan does **not** redesign MEMORY or Affect.

For v108 decomposition:

- memory is accessed through a coordinator/port but keeps existing provenance
  and MemoryUseGate semantics;
- affect is projected through a coordinator/port but remains governed by
  `AFFECT_ENGINE_CONVERGENCE_PLAN.md`;
- no new durable affect authority is introduced here;
- no private MEMORY is added to source control;
- no module is promoted from advisory to canonical merely because it moved
  behind a new interface.

This prevents an engine refactor from silently changing autobiographical or
affective truth semantics.

## 11. Failure signatures and operational learning

Generate a stable failure signature from bounded technical fields, e.g.:

```text
stage
+ component
+ reason_code
+ route
+ handler
+ validator_code
```

Do not hash raw private user content into a globally reusable fingerprint unless
the existing privacy contract permits it.

OperationalLearningMemory may record:

- failure signature;
- first seen / last seen;
- recurrence count;
- fixed-in version;
- regression-test id;
- resolution status.

If a failure marked fixed reappears after the fixing release:

`REGRESSION_DETECTED`

The learning record does not modify code automatically.

## 12. User-visible error policy

Normal user-facing output stays concise.

Example:

> Nie udało się domknąć tej trasy: zatrzymała się na etapie pamięci. Nie będę zgadywać. Kod diagnostyczny: `JAZN-TURN-...`.

Full technical detail remains available through diagnostics/status tooling:

```text
turn_id
trace_id
failure stage
module/symbol
route lineage
fallback lineage
repair attempts
validator outcome
finalization state
```

Do not expose raw private chain-of-thought. Diagnostics contain operational
events, decisions and evidence only.

## 13. Recommended release sequence

Do not deliver the entire decomposition as one giant PR.

### v108 — diagnostic spine + extraction seams

- `TurnDiagnosticTrace`;
- typed fallback taxonomy;
- BlindRouteDetector;
- static RouteGraphAudit;
- characterization tests;
- `EngineServices` interfaces/wrappers;
- no intended behavioral change to successful turns.

### v109 — constructor/lifecycle + finalization extraction

- remove persistent side effects from engine construction;
- extract `FinalizationService`;
- change phase-2 host finalization to avoid full-engine construction;
- parity and restart tests.

### v110 — turn orchestration decomposition

- ContextCoordinator;
- CognitiveFrameBuilder;
- DialogueRouter;
- ResponsePipeline;
- ValidationPipeline;
- RecoveryPolicy;
- PersistenceCoordinator;
- `JaznEngine` becomes a thin compatibility facade over the canonical
  `TurnOrchestrator`.

### v111 — legacy dialogue reduction / canonical switch

- migrate remaining ordinary-conversation branches from
  `conversation.py`;
- canonical structured response plans + model/NLG realization;
- remove dead/unreachable compatibility branches after soak evidence.

Version numbers remain provisional until each implementation branch starts from
fresh `master`.

## 14. Tests

Minimum new test families:

### Diagnostic contract

- one ordered event sequence per turn;
- event_seq strictly monotonic;
- failure always has stage + component + reason_code;
- fallback always has from/to lineage;
- terminal diagnostics cannot render Jaźń voice.

### Route graph

- all classifier intents resolve;
- all registry handlers exist;
- all active handlers are reachable or explicitly compatibility-only;
- required component ownership is complete;
- no anonymous generic fallback in critical routes.

### Engine characterization/parity

For representative route families compare old/current behavior against extracted
components:

- selected intent/route/handler;
- required component set;
- memory-use decision;
- truth/provenance outcome;
- fallback/repair outcome;
- final-response contract;
- accepted-visible-turn semantics.

Exact natural-language equality is required only where the old contract is
itself deterministic/protocol text.

### Failure injection

Inject failures at:

- context/memory retrieval;
- route handler;
- model/provider;
- tool capability;
- validator;
- finalization;
- persistence.

Each injected failure must terminate in exactly one documented fallback or
terminal state.

### Lifecycle

- engine construction does not mutate persistent state after Phase C;
- supervisor/daemon/session behavior is unchanged;
- finalization does not construct a full engine after Phase H.

### Cross-platform/release

Existing required gates remain:

- compileall;
- Pyright;
- non-live pytest;
- persistent-runtime-e2e Windows/Linux;
- PowerShell regressions;
- package-distribution cleanroom;
- release-hardening / metadata sync;
- package smoke.

## 15. Metrics / code-health gates

Track trends rather than rewarding arbitrary file splitting:

- `engine.py` total bytes/lines;
- size of `JaznEngine.__init__`;
- size of `JaznEngine.process_turn`;
- number of persistent side effects during construction;
- number of fallback sites with typed reason;
- anonymous fallback count;
- unreachable route/handler count;
- finalization dependencies count;
- route-repair rate;
- fallback rate by reason;
- rejected-finalization rate;
- regression recurrence count.

Do not pass a gate by moving unchanged monolithic code into one equally
monolithic helper.

## 16. Exit criteria for the whole program

The decomposition program is complete only when:

1. `ConversationRunner` remains the single session/turn owner.
2. `JaznEngine` is a thin compatibility/composition facade or is no longer
   required by canonical callers.
3. Engine construction is side-effect free.
4. Host finalization does not instantiate the full cognitive engine.
5. Every fallback has typed origin/reason/from/to lineage.
6. Every failed/repair attempt remains visible in one canonical turn trace.
7. Static route audit reports no unexplained blind paths.
8. Normal conversational generation no longer depends on large hard-coded
   paragraph mappings in `conversation.py`.
9. MEMORY, Affect, identity and accepted-visible-turn truth boundaries remain
   unchanged unless their own owner plans explicitly change them.
10. Windows/Linux CI, package/release gates and real host E2E remain green.

## 17. Immediate next implementation step

The first code branch after this planning branch should start from the then
current `master` and implement only **v108 diagnostic spine + extraction
seams**.

Do not begin by moving hundreds of lines out of `engine.py`.

First make failures observable enough that every later extraction can prove:

```text
same input
-> same intended route/evidence
-> same accepted behavior
or
-> explicit, attributable difference
```

That diagnostic spine is the safety harness for the rest of the rewrite.
