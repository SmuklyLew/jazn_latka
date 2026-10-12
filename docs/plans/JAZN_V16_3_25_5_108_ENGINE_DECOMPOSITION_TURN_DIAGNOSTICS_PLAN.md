# Jaźń v16.3.25.5.108 → v16.3.25.5.111 — pełny plan dekompozycji JaznEngine, diagnostyki tras i kanonicznego ConversationRunner

**Status:** `IMPLEMENTATION_COMPLETE_REPOSITORY_AND_REAL_HOST_E2E`  
**Data:** 2026-10-06  
**Baseline repo:** `SmuklyLew/jazn_latka`  
**Baseline:** `master @ 712a25db94c634ea47fbf265c0d907608a668f00`  
**Baseline release:** `16.3.25.5.107-persistent-remote-runtime-operations-convergence`  
**Zakres logiczny:** v108 → v111  
**Parent plans:** `CONVERSATION_RUNTIME_CONVERGENCE_PLAN.md`, `CONVERSATION_RUNTIME_TEST_AND_MIGRATION_MATRIX.md`  
**Related plans:** `AFFECT_ENGINE_CONVERGENCE_PLAN.md`, `LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`  
**Zasada migracji:** add → shadow/parity → canonical switch → soak → remove legacy

> Ten program nie tworzy drugiego runtime, drugiego ownera sesji, drugiej pamięci,
> drugiej authority afektu ani drugiej finalizacji. Rozcina istniejący system
> wzdłuż już istniejących kontraktów i dodaje jeden wspólny ślad diagnostyczny,
> tak aby każda awaria, naprawa i fallback wskazywały dokładne miejsce oraz
> przyczynę.

---

# 1. Streszczenie wykonawcze

v107 domknął warstwę persistent remote runtime operations: strict readiness,
canonical supervisor ownership, osobne liveness/readiness, publiczny MCP
deployment contract i producer-side MEMORY exact-set verification.

Następny problem nie polega na braku kolejnej capability. Jest nim **zbyt duża
koncentracja odpowiedzialności w `JaznEngine` oraz rozproszona diagnostyka
tury**.

Aktualny `latka_jazn/core/engine.py` ma około 217 KB i jednocześnie uczestniczy
w:

- składaniu zależności;
- uruchamianiu części lifecycle;
- context/cognitive-frame;
- pamięci;
- NLP i routingu;
- afekcie/self-state;
- generowaniu odpowiedzi;
- walidacji;
- recovery;
- provenance;
- persistence;
- finalization;
- audycie.

Jednocześnie:

- `JaznEngine.__init__` nadal wykonuje side-effecty;
- `conversation.py` pozostaje dużą legacy powierzchnią routingu i gotowych
  odpowiedzi;
- phase-2 host finalization tworzy pełny `JaznEngine` tylko po to, by utrwalić
  gotowy kandydat;
- `TurnRouteTrace`, `RouteDispatchReport`, `RuntimeAnswerValidator`,
  provenance, `TurnExecutionContext` i audit stores mają przydatne evidence,
  ale nie składają się jeszcze w **jeden kanoniczny turn-root trace**;
- nie istnieje jeden statyczny gate potwierdzający, że wszystkie intenty, routes,
  handlery i wymagane komponenty tworzą domknięty graf.

Program v108–v111 ma zakończyć ten stan.

Docelowo:

```text
run.py                      # thin launcher
  |
main.py                     # central control plane
  |
ConversationRunner          # single session/turn owner
  |
TurnStateMachine            # canonical state of one logical turn
  |
TurnOrchestrator
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

`JaznEngine` przechodzi z roli "god object" do cienkiej fasady compatibility,
a następnie przestaje być właścicielem przepływu.

---

# 2. Granica zakresu

## 2.1 Co ten program zmienia

- obserwowalność całej tury;
- klasyfikację błędów/fallbacków;
- graf routingu i jego CI audit;
- composition/dependency ownership;
- lifecycle konstrukcji `JaznEngine`;
- host finalization ownership;
- wewnętrzną orkiestrację tury;
- outer conversation ownership;
- sposób migracji legacy `conversation.py`;
- testy parity, failure injection, rollback i soak.

## 2.2 Czego ten program nie redefiniuje

Nie zmieniamy tutaj samodzielnie:

- autobiographical MEMORY truth semantics;
- canonical Affect V2 semantics;
- identity canon;
- accepted-visible-turn truth boundary;
- MCP auth policy;
- daemon/supervisor ownership z v107;
- publicznego endpointu i infrastruktury operatora;
- model provider semantics poza adapter boundary.

Memory i Affect są używane przez nowe porty/coordinators, ale ich własne
authority pozostają w ich kanonicznych planach.

---

# 3. Potwierdzony baseline v107

Na `master @ 712a25db94c634ea47fbf265c0d907608a668f00`:

1. `run.py` jest thin launcherem, `main.py` centralnym control plane.
2. v107 jest scalone przez PR #317.
3. remote MCP deployment wymaga canonical nested readiness i verified supervisor.
4. MEMORY v3 producer wykonuje exact-set self-verification przed transportem.
5. `JaznRuntimeSession` jest wspólnym rdzeniem one-shot/chat/chat-gpt.
6. `TurnExecutionContext` już przechowuje turn-local telemetry, cancellation i
   delayed semantic persistence.
7. `TurnRouteTrace` istnieje i jest wytwarzany w `JaznEngine.process_turn`.
8. `RouteHandlerDispatcher` już zapisuje `handler_error` i nie udaje sukcesu
   handlera po wyjątku.
9. `RuntimeAnswerValidator` i repair synthesis już rozróżniają część błędów
   jakościowych.
10. `chat_command_contract.py` nadal tworzy pełny `JaznEngine` w phase-2
    finalization.
11. `ConversationRunner` i `TurnStateMachine` istnieją jeszcze jako planowany
    target, nie jako canonical implementation.
12. `conversation.py` nadal zawiera legacy phrase/route/response logic.

---

# 4. Research / evidence base

Poniższe źródła uzasadniają kierunki architektoniczne. Nie są kopiowane jako
gotowy projekt Jaźni.

## 4.1 MCP 2026-07-28 — stateless protocol i durable tasks

Oficjalne materiały MCP dla rewizji 2026-07-28 opisują:

- nowy stateless lifecycle;
- `server/discover` zamiast starego handshake jako model modern era;
- protocol/capabilities niesione per request;
- Tasks extension jako durable state machine z pollingiem;
- wymaganie, aby task był trwale utworzony zanim server zwróci jego handle.

Źródła:

- https://py.sdk.modelcontextprotocol.io/protocol-versions/
- https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28
- https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks
- https://plan.modelcontextprotocol.io/conformance/1

**Wniosek dla Jaźni:** remote ingress nie może polegać na ukrytym stanie
transportowej sesji. `request_id/turn_id/trace_id` oraz capability evidence
muszą być jawne. Długie wykonanie może mapować się na durable task, ale logical
turn nadal ma dokładnie jednego ownera.

## 4.2 OpenAI Agents SDK — jeden runner, sessions, lifecycle hooks, tracing

Oficjalna dokumentacja OpenAI Agents SDK pokazuje prosty podział:

- runner zarządza przebiegiem;
- sessions utrzymują wieloturowy kontekst;
- lifecycle hooks obserwują agent/model/tool/handoff;
- tracing daje jeden end-to-end workflow trace z podzdarzeniami/spans.

Źródła:

- https://openai.github.io/openai-agents-python/
- https://openai.github.io/openai-agents-python/sessions/
- https://openai.github.io/openai-agents-python/tracing/
- https://openai.github.io/openai-agents-python/agents/
- https://openai.github.io/openai-agents-python/ref/lifecycle/

**Wniosek dla Jaźni:** `ConversationRunner` powinien być jednym ownerem
przepływu, a model/tool adapters wykonawcami. Obserwowalność powinna obejmować
cały run, nie być rozbita na niezależne logi każdego modułu.

## 4.3 OpenTelemetry — trace, events, errors i privacy-aware telemetry

OpenTelemetry definiuje:

- trace/span jako end-to-end operation;
- uporządkowane zdarzenia na span;
- `error.type` jako stabilny klasyfikator awarii;
- osobne exception attributes;
- zasadę niedublowania tej samej awarii w wielu miejscach;
- rozróżnienie między błędem końcowej operacji a błędem obsłużonym po drodze.

Źródła:

- https://opentelemetry.io/docs/specs/otel/trace/api/
- https://opentelemetry.io/docs/specs/semconv/general/recording-errors/
- https://opentelemetry.io/docs/specs/semconv/exceptions/
- https://opentelemetry.io/docs/specs/semconv/registry/attributes/exception/
- https://opentelemetry.io/docs/specs/otel/error-handling/

**Wniosek dla Jaźni:** `TurnDiagnosticTrace` powinien mieć uporządkowany
`event_seq`, jeden końcowy outcome, typed `error_type/reason_code` i brak
wielokrotnego rejestrowania tej samej awarii.

## 4.4 W3C Trace Context — interoperacyjny trace i brak PII w trace metadata

W3C Trace Context definiuje przenoszenie `traceparent` / `tracestate` między
systemami i jawnie ostrzega przed PII w `tracestate`.

Źródło:

- https://www.w3.org/TR/trace-context/

**Wniosek dla Jaźni:** runtime może eksportować bounded trace context przez MCP,
ale zewnętrzna telemetry nie zawiera raw user text, memory excerpts ani danych
osobistych. Identyfikatory tury są wystarczające.

## 4.5 Google SRE — retry budget, jedna warstwa retry, graceful degradation

Google SRE zaleca:

- exponential backoff z jitter;
- ograniczone retry budgets;
- retry tylko na właściwej warstwie, aby nie tworzyć multiplikacji;
- graceful degradation zamiast przeciążenia całego systemu;
- monitoring jako źródło diagnostyki przyczyn, nie tylko "service up/down";
- testowanie failure/overload paths.

Źródła:

- https://sre.google/sre-book/service-best-practices/
- https://sre.google/sre-book/handling-overload/
- https://sre.google/sre-book/addressing-cascading-failures/
- https://sre.google/workbook/monitoring/
- https://sre.google/workbook/alerting-on-slos/

**Wniosek dla Jaźni:** retry/fallback ownership musi być pojedynczy i jawny.
Transport nie replayuje user message. Recovery jest bounded. Graceful
degradation ma osobną klasę od terminal failure.

## 4.6 Strangler Fig — gradual replacement zamiast cut-over rewrite

Martin Fowler opisuje gradual replacement jako sposób zmniejszenia ryzyka przy
modernizacji krytycznego systemu.

Źródła:

- https://martinfowler.com/bliki/StranglerFigApplication.html
- https://martinfowler.com/articles/2024-strangler-fig-rewrite.html

**Wniosek dla Jaźni:** `JaznEngine` nie jest przepisywany od zera. Nowe
komponenty są dokładane obok starego path, mierzone w parity/shadow, następnie
przejmują ownership, a legacy jest usuwane dopiero po soak.

---

# 5. Niezmienniki całego programu v108–v111

## INV-108-01 — jeden owner logical turn

Dla jednego `turn_id` istnieje dokładnie jeden owner. Model, handler, MCP task
ani host nie stają się osobnym ownerem.

## INV-108-02 — one input → one logical turn

Retry/poll/resume nigdy nie tworzą drugiej tury z tego samego user message.

## INV-108-03 — jedna accepted visible final

Dla jednej revision tury istnieje maksymalnie jeden accepted
`final_visible_text`.

## INV-108-04 — brak silent fallback

Każdy fallback ma typed origin, reason, from/to lineage i disposition.

## INV-108-05 — brak utraty wcześniejszego błędu

Repair attempt nie nadpisuje informacji o odrzuconym attempt 0.

## INV-108-06 — diagnostics ≠ chain-of-thought

Trace zawiera operacyjne zdarzenia, decyzje, klasy błędów, evidence refs i
wyniki gate'ów. Nie zapisuje prywatnego toku rozumowania modelu.

## INV-108-07 — telemetry nie jest pamięcią autobiograficzną

Audit/trace nie może zostać automatycznie promowany do MEMORY jako primary
source.

## INV-108-08 — constructor nie jest lifecycle

Po v109 samo skonstruowanie engine/services nie zapisuje stanu ani nie
uruchamia pracy tła.

## INV-108-09 — model/provider nie posiada session truth

Provider continuation IDs są metadata adaptera. Session/turn truth należy do
Jaźni.

## INV-108-10 — no automatic old-engine fallback

Po canonical switch błąd nowej ścieżki nie może po cichu przełączać tury na
stary engine. Legacy path jest tylko jawnie sterowanym compatibility/rollback
mode podczas migracji.

---

# 6. Wspólny kontrakt diagnostyczny

## 6.1 Nowy moduł

Planowany moduł:

`latka_jazn/core/turn_diagnostics.py`

Możliwe pomocnicze moduły:

```text
latka_jazn/core/failure_taxonomy.py
latka_jazn/core/blind_route_detector.py
latka_jazn/core/route_graph_contract.py
```

Nie mnożyć plików, jeżeli implementacja pozostaje czytelniejsza w jednym
module.

## 6.2 TurnStage

Minimalny zamknięty katalog:

```text
INGRESS
TURN_BINDING
CONTEXT
MEMORY
COGNITION
AFFECT
ROUTING
HANDLER
MODEL
TOOL
VALIDATION
RECOVERY
FINALIZATION
PERSISTENCE
PRESENTATION
SETTLEMENT
```

Nowe stage wymagają testu i uzasadnienia.

## 6.3 FailureKind

Minimalne typy:

```text
INVALID_INPUT
CAPABILITY_UNAVAILABLE
DEPENDENCY_NOT_READY
TIMEOUT
CANCELLED
CONTRACT_VIOLATION
LINEAGE_MISMATCH
ROUTE_UNRESOLVED
HANDLER_EXCEPTION
REQUIRED_COMPONENT_MISSING
MEMORY_EVIDENCE_UNAVAILABLE
MODEL_UNAVAILABLE
TOOL_UNAVAILABLE
VALIDATION_REJECTED
FINALIZATION_REJECTED
PERSISTENCE_FAILED
DUPLICATE_ACCEPTED_FINAL
INTERNAL_INVARIANT_BROKEN
```

## 6.4 FallbackKind

Tylko trzy wysokopoziomowe dispositions:

```text
RECOVERABLE_FALLBACK
EXTERNAL_CAPABILITY_REQUIRED
TERMINAL_DIAGNOSTIC
```

### RECOVERABLE_FALLBACK

Istnieje bounded, legalna alternatywa w tej samej turze.

### EXTERNAL_CAPABILITY_REQUIRED

Tura pozostaje związana, ale wymaga host/model/tool result i będzie resume'owana
tym samym `request_id/turn_id`.

### TERMINAL_DIAGNOSTIC

Kontynuacja mogłaby sfałszować lineage, truth lub accepted-final state. Tura
kończy się techniczną diagnozą.

## 6.5 DiagnosticEvent

Proponowany kontrakt:

```python
@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    seq: int
    timestamp_utc: str
    stage: TurnStage
    component: str
    event_type: str
    outcome: str
    reason_code: str | None
    attributes: Mapping[str, JsonValue]
```

`attributes` ma allowlistę i nie przechowuje raw promptów/memory excerpts.

## 6.6 TurnDiagnosticTrace

Proponowany root:

```python
@dataclass(slots=True)
class TurnDiagnosticTrace:
    schema_version: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    revision: int
    events: list[DiagnosticEvent]
    selected_intent: str | None
    selected_route: str | None
    selected_handler: str | None
    fallback: FallbackDecision | None
    final_outcome: str | None
    failure_signature: str | None
```

Wewnętrzny exact-input fingerprint może pozostać w idempotency store. Nie
eksportować go automatycznie do remote telemetry.

## 6.7 FallbackDecision

```python
@dataclass(frozen=True, slots=True)
class FallbackDecision:
    kind: FallbackKind
    origin_stage: TurnStage
    origin_component: str
    reason_code: str
    from_route: str | None
    to_route: str | None
    recoverable: bool
    required_capability: str | None
    attempt: int
    evidence_refs: tuple[str, ...]
```

## 6.8 FailureSignature

Stabilny techniczny signature:

```text
stage
+ component
+ reason_code
+ route
+ handler
+ validator_code
```

Signature nie zawiera raw user text.

---

# 7. Canonical TurnStateMachine

Najpóźniej w v111 każda tura ma jeden jawny state machine.

## 7.1 Stany

```text
RECEIVED
BOUND
CONTEXT_BUILDING
CONTEXT_READY
ROUTING
EXECUTING
WAITING_EXTERNAL
VALIDATING
RECOVERING
AWAITING_FINALIZATION
COMMITTING
ACCEPTED
FAILED_TERMINAL
CANCELLED
EXPIRED
```

## 7.2 Legalne przejścia

Przykład głównej ścieżki:

```text
RECEIVED
→ BOUND
→ CONTEXT_BUILDING
→ CONTEXT_READY
→ ROUTING
→ EXECUTING
→ VALIDATING
→ AWAITING_FINALIZATION
→ COMMITTING
→ ACCEPTED
```

Host-model:

```text
EXECUTING
→ WAITING_EXTERNAL
→ EXECUTING
→ VALIDATING
```

Repair:

```text
VALIDATING
→ RECOVERING
→ EXECUTING
→ VALIDATING
```

Terminal:

```text
any non-terminal state
→ FAILED_TERMINAL
```

Nielegalne:

```text
ACCEPTED → anything
FAILED_TERMINAL → EXECUTING
WAITING_EXTERNAL → RECEIVED
COMMITTING → ROUTING
```

## 7.3 Attempt vs turn

Retry/repair tworzy `attempt + 1`, nie nowy `turn_id`.

Transport retry/poll nie zwiększa attempt, jeśli backend nie rozpoczął nowego
wykonania.

---

# 7.4 Current v108 implementation evidence

Implementation branch:
`upgrade/v16.3.25.5.108-engine-decomposition-turn-diagnostics-convergence`.

Current candidate includes:

- canonical turn-root `TurnDiagnosticTrace` owned by `TurnExecutionContext`;
- typed fallback/failure taxonomy and fallback history;
- explicit unresolved-handler and handler-exception fallback evidence;
- `BlindRouteDetector`;
- static `RouteGraphAudit` plus operator/CI command;
- `EngineServices` extraction seams without ownership transfer;
- route/handler/validation/repair/finalization/persistence diagnostic events;
- privacy-bounded diagnostics;
- v108 characterization and failure-injection regressions;
- explicit release-hardening and cross-platform persistent-runtime CI gates.

This is implementation evidence, not a PASS declaration. Merge readiness requires
the same final PR HEAD to pass the gates listed below.

# 8. v108 — Diagnostic Spine + No-Silent-Fallback + Extraction Seams

**Target:** `16.3.25.5.108-engine-decomposition-turn-diagnostics-convergence`

## 8.1 Cel

Zanim przeniesiemy logikę z `engine.py`, system ma umieć powiedzieć:

- gdzie weszła tura;
- jaki intent/route/handler wybrano;
- czego oczekiwano;
- jakie komponenty faktycznie powstały;
- gdzie pojawiło się odchylenie;
- czy wykonano repair;
- dlaczego użyto fallbacku;
- jaki był finalny outcome.

v108 nie ma celowo zmieniać udanych odpowiedzi.

## 8.2 Implementacja

### A. TurnDiagnosticTrace

Dodać kontrakty z sekcji 6.

Integracja z:

- `TurnExecutionContext`;
- `JaznRuntimeSession`;
- `JaznEngine.process_turn`;
- `TurnRouteTrace`;
- `RouteHandlerDispatcher`;
- `RuntimeAnswerValidator`;
- host finalization;
- persistence/settlement.

`TurnRouteTrace` pozostaje compatibility projection.

### B. No-silent-fallback

Znaleźć wszystkie miejsca ustawiające:

```text
fallback
cannot_answer_directly
handler_error
null_fallback
repair_synthesis
model unavailable
tool unavailable
```

Każde mapować do typed `FallbackDecision`.

CI ma odrzucać nowe anonymous fallback sites.

### C. BlindRouteDetector

Runtime detector sprawdza po każdej turze:

- intent istnieje;
- route istnieje;
- handler istnieje;
- wybrany handler rzeczywiście został wywołany;
- wymagane komponenty mają ownera;
- wymagane komponenty są produced albo explicitly unavailable;
- validator rejection wskazuje konkretny reason;
- fallback ma pełną lineage;
- finalization nie usuwa wcześniejszej przyczyny awarii.

### D. RouteGraphAudit

Planowany tool:

`python -X utf8 -m latka_jazn.tools.route_graph_audit --json`

Graf:

```text
DialogueIntentClassifier
→ RouteRegistry
→ RouteHandlerDispatcher
→ handler required components
→ RuntimeAnswerValidator requirements
```

Gate:

```text
unresolved_intents == 0
routes_without_handlers == 0
anonymous_fallbacks == 0
required_components_without_owner == 0
duplicate_canonical_owners == 0
unreachable_handlers == 0
  OR explicit compatibility_allowlist
```

### E. Characterization fixtures

Przed dekompozycją zamrozić reprezentatywne cases:

```text
ordinary dialogue
self-state
identity
runtime status/source
memory recall
memory unavailable
tool required
model required
handler exception
validator mismatch
repair success
repair failure
host finalization success
host finalization rejection
timeout
duplicate request
```

Porównywać contracts, nie wyłącznie tekst.

### F. EngineServices seams

Dodać interfaces/wrappers bez przejęcia ownership:

```python
@dataclass(slots=True)
class EngineServices:
    diagnostics: TurnDiagnostics
    memory: MemoryCoordinatorPort
    cognition: CognitionPort
    routing: RoutingPort
    affect: AffectPort
    generation: GenerationPort
    validation: ValidationPort
    recovery: RecoveryPort
    finalization: FinalizationPort
    persistence: PersistencePort
```

Na v108 porty mogą opakowywać stare obiekty.

## 8.3 Testy v108

Nowe rodziny:

```text
test_turn_diagnostic_trace.py
test_turn_diagnostic_event_order.py
test_turn_failure_taxonomy.py
test_no_silent_fallback.py
test_blind_route_detector.py
test_route_graph_audit.py
test_turn_diagnostic_privacy.py
test_failure_injection_matrix.py
test_turn_trace_finalization_binding.py
```

Failure injection:

- handler raises;
- memory gateway unavailable;
- model adapter unavailable;
- tool capability unavailable;
- validator rejects;
- finalization lineage mismatch;
- persistence write fails;
- timeout/cancel.

Każdy przypadek musi skończyć się dokładnie jednym final disposition.

## 8.4 Observability v108

Minimalne liczniki:

```text
turns_total
turns_accepted_total
turns_terminal_total
fallback_total{kind,reason}
repair_total{reason,outcome}
blind_route_total{reason}
validation_reject_total{code}
finalization_reject_total{code}
turn_duration_ms{outcome}
stage_duration_ms{stage}
```

Nie wprowadzać obowiązkowej zależności OpenTelemetry SDK do core. Struktura ma
być OTEL-compatible, ale eksport jest optional adapter/capability.

## 8.5 Rollback v108

v108 nie zmienia canonical engine ownership.

Jeżeli diagnostics powoduje regresję:

- można wyłączyć export/persistence diagnostics;
- nie wolno wyłączyć truth/finalization;
- runtime trace może pozostać in-memory;
- stary `TurnRouteTrace` nadal działa jako compatibility projection.

## 8.6 Exit gate v108

```text
one TurnDiagnosticTrace per logical turn              PASS
event_seq monotonic                                  PASS
one terminal/final outcome                           PASS
anonymous fallback                                   0
critical fallback without from/to lineage            0
unresolved intents                                   0
routes without handlers                              0
required components without owner                    0
unexplained unreachable active handlers              0
characterization corpus                              PASS
successful-turn contract parity                      PASS
diagnostic raw-private-text leakage                  0
compileall                                           PASS
Pyright                                              PASS
non-live pytest                                      PASS
Windows/Linux persistent-runtime CI                  PASS
release-hardening / manifest sync                    PASS
```

---

# 9. v109 — Side-Effect-Free Construction + Finalization Extraction

**Target:** `16.3.25.5.109-engine-lifecycle-finalization-decomposition-convergence`

## 9.1 Cel

Odciąć dwie największe przeszkody do dalszej dekompozycji:

1. konstruktor engine wykonujący lifecycle/side-effecty;
2. phase-2 finalization zależne od pełnego cognitive engine.

## 9.2 RuntimeCompositionRoot

Dodać jeden composition root, nie drugi control plane.

Proponowany moduł:

`latka_jazn/core/runtime_composition.py`

Rola:

- zbudować stores/services;
- zweryfikować dependencies;
- wykonać jawny hydrate/start;
- przekazać gotowe services do session/runner;
- wykonać jawny close.

Nie może:

- parsować publicznego CLI;
- przejąć `main.py`;
- tworzyć własnej sesji równolegle z daemonem.

## 9.3 JaznEngine construction

Target:

```python
services = RuntimeCompositionRoot(config).build()
engine = JaznEngine(services)
```

Samo:

```python
JaznEngine(services)
```

nie może:

- zapisywać `engine_started`;
- seedować procedur;
- budować/zapisywać project index;
- wykonywać migracji;
- tworzyć background job;
- mutować MEMORY/core state.

Lifecycle:

```text
build
→ validate
→ hydrate
→ start
→ process
→ close
```

## 9.4 Procedural seeding

`_seed_core_procedures()` przenieść do jawnego bootstrap/migration service.

Dodatkowo:

- wprowadzić stabilny `rule_id`;
- wersja release jest metadata revision, nie identity;
- user-specific rules nie powinny być hard-coded w engine constructor;
- istniejące reguły wymagają inventory: canonical system rule vs memory/profile
  data vs historical compatibility.

Nie usuwać historycznych danych bez migration evidence.

## 9.5 ProjectStartupIndexer

Project index build/write:

- nie w constructor;
- jawny startup stage;
- cache/invalidation ma własny reason;
- failure daje `DEPENDENCY_NOT_READY` albo degraded mode zależnie od tego, czy
  indeks jest krytyczny dla konkretnej trasy.

## 9.6 FinalizationService

Nowy narrow service:

`latka_jazn/core/finalization_service.py`

Minimalne dependencies:

```text
pending turn store
lineage/binding verifier
final candidate validator
final response contract
MessageEnvelope builder
accepted-visible persistence
session/conversation settlement
diagnostics/audit
```

Nie zależy od:

```text
DialogueIntentClassifier
ProjectStartupIndexer
memory retrieval
AffectiveGranularityModel
general routing
NLP pipeline
model adapter
```

## 9.7 chat_command_contract migration

Obecne:

```text
persist host reply
→ construct full JaznEngine
→ engine.persist_final_visible_reply(...)
```

Target:

```text
persist host reply
→ FinalizationService.finalize(...)
```

Ten sam binding:

```text
request_id
turn_id
trace_id
timestamp/contract binding
candidate digest
MessageEnvelope
accepted finalization
```

## 9.8 Finalization state

FinalizationService ma rozróżniać:

```text
CANDIDATE_RECEIVED
BINDING_VERIFIED
CANDIDATE_VALIDATED
FINAL_CONTRACT_BUILT
PERSISTENCE_PREPARED
COMMIT_ACCEPTED
VISIBLE_ACCEPTED
```

Błąd przed `COMMIT_ACCEPTED` nie może pozostawić accepted-visible artefact.

## 9.9 Testy v109

```text
test_engine_construction_no_persistent_writes.py
test_engine_construction_no_project_index_write.py
test_runtime_composition_lifecycle.py
test_procedural_seed_idempotency.py
test_procedural_rule_identity.py
test_finalization_service_success.py
test_finalization_service_lineage_mismatch.py
test_finalization_service_stale_binding.py
test_finalization_service_duplicate_final.py
test_finalization_service_persistence_failure.py
test_chat_command_phase2_without_engine_construction.py
test_finalization_crash_atomicity.py
```

Specjalny gate:

`chat_command_contract.py` nie może importować/konstruować `JaznEngine` dla
phase-2 finalization.

## 9.10 Rollback v109

Compatibility facade `JaznEngine.persist_final_visible_reply` może przez jeden
release delegować do `FinalizationService`.

Nie może istnieć automatyczny reverse fallback z FinalizationService do starej
implementacji po błędzie. Rollback jest release/operator action.

## 9.11 Exit gate v109

```text
JaznEngine construction persistent side effects        0
phase2 full-engine construction                         0
FinalizationService external cognitive dependencies     0
duplicate accepted final                                0
crash-before-commit durable accepted artefact           0
procedural seed duplicate identity                      0
v108 diagnostic gates                                   PASS
existing accepted-visible-turn tests                    PASS
Windows/Linux                                           PASS
Pyright/release-hardening                               PASS
```

---

# 10. v110 — TurnOrchestrator + Decomposition of JaznEngine.process_turn

**Target:** `16.3.25.5.110-turn-orchestrator-engine-decomposition-convergence`

## 10.1 Cel

Przenieść właściwy przebieg jednej tury z monolitycznego
`JaznEngine.process_turn` do jawnych, małych komponentów.

`JaznEngine` staje się compatibility facade.

## 10.2 TurnOrchestrator

Nowy moduł:

`latka_jazn/core/turn_orchestrator.py`

Proponowany interfejs:

```python
class TurnOrchestrator:
    def process(self, request: TurnRequest, context: TurnExecutionContext) -> TurnResult:
        ...
```

Pseudo-flow:

```python
def process(request, turn_context):
    context = context_coordinator.build(request, turn_context)
    frame = cognitive_frame_builder.build(context)
    route = dialogue_router.resolve(frame)
    execution = dialogue_router.execute(route, frame)
    candidate = response_pipeline.produce(execution, frame)
    validation = validation_pipeline.validate(candidate, frame)

    if not validation.accepted:
        recovery = recovery_policy.resolve(validation, frame)
        if recovery.terminal:
            return terminal_result(recovery)
        candidate = response_pipeline.recover(recovery, frame)
        validation = validation_pipeline.validate(candidate, frame)

    return persistence_coordinator.prepare_result(
        frame=frame,
        candidate=candidate,
        validation=validation,
    )
```

Host finalization nadal jest osobnym phase-2 service.

## 10.3 ContextCoordinator

Owner:

- normalized user input reference;
- session history snapshot;
- task state;
- prior accepted turn references;
- capability snapshot;
- time/deadline;
- memory availability status;
- existing wake/session state.

Nie wykonuje:

- final generation;
- memory promotion;
- final persistence.

## 10.4 CognitiveFrameBuilder

Integruje istniejące:

- Polish/NLP evidence;
- reasoning plan;
- salience;
- temporal semantics;
- self-state projection;
- affect projection;
- capability/truth constraints.

Ma zwracać typed `CognitiveFrame`, nie mutować globalnego engine.

## 10.5 MemoryCoordinator

Adapter wokół istniejących:

```text
MemorySearchPlanner
LivingMemoryGateway
MemoryUseGate
source/provenance contracts
```

Interfejs:

```python
MemoryProbeResult probe(MemoryProbeRequest)
```

Wynik:

```text
items
source classes
eligibility
abstention reason
provenance refs
readiness
diagnostics
```

MemoryCoordinator nie zmienia pamięciowego truth contract.

## 10.6 AffectCoordinator

Na v110 jest **port/projection**, nie nowa Affect V2 authority.

Interfejs:

```python
AffectProjection evaluate(AffectRequest)
```

Może używać obecnych modułów, ale:

- nie tworzy drugiego durable affect state;
- nie zmienia `AFFECT_ENGINE_CONVERGENCE_PLAN`;
- jawnie raportuje źródło/advisory/canonical status.

## 10.7 DialogueRouter

Owija:

```text
DialogueIntentClassifier
RouteRegistry
RouteHandlerDispatcher
```

Interfejs:

```python
RouteDecision resolve(RouteRequest)
RouteExecution execute(RouteDecision)
```

Każdy `RouteDecision` ma:

```text
intent
route
handler
support/confidence semantics
required components
reason codes
fallback policy
```

## 10.8 ResponsePipeline

Oddziela **co odpowiedzieć** od **jak sformułować tekst**.

Planowany model:

```text
handler evidence / structured result
→ ResponsePlan
→ deterministic protocol realizer
  OR model-guided NLG
→ ResponseCandidate
```

`ResponsePlan`:

```text
facts/evidence refs
required points
forbidden claims
truth constraints
source constraints
tone/style hints
tool/model requirements
```

Naturalny model nie może zmienić source truth.

## 10.9 ValidationPipeline

Składa:

- required-components;
- runtime answer validation;
- source/provenance validation;
- epistemic guard;
- final response contract eligibility.

Wynik:

```python
ValidationResult(
    accepted: bool,
    violations: tuple[ValidationViolation, ...],
    repair_allowed: bool,
    terminal: bool,
)
```

## 10.10 RecoveryPolicy

Jedyny owner decyzji:

```text
repair
external capability
graceful degradation
terminal diagnostic
```

Nie może być retry/fallback logic rozproszony w handlerach, validatorze i host
bridge bez raportowania do policy.

## 10.11 PersistenceCoordinator

Rozróżnia:

```text
candidate produced
candidate validated
turn awaiting host finalization
accepted final
session state commit
conversation state commit
eligible memory projection
eligible affect commit (wg osobnego Affect contract)
```

Nie commituje accepted state przed właściwym gate.

## 10.12 JaznEngine facade

Po v110:

```python
class JaznEngine:
    def __init__(self, services):
        self._orchestrator = services.turn_orchestrator

    def process_turn(self, text, *, client_context=None):
        request = legacy_request_adapter(text, client_context)
        return self._orchestrator.process(request)
```

Facade nie buduje dependencies.

## 10.13 Shadow/parity

Podczas developmentu:

```text
canonical current result
+
shadow new pipeline result
→ compare contracts
```

Shadow nie może:

- wykonywać tool side effects;
- pisać do MEMORY;
- wykonywać duplicate model calls w normalnym release;
- commitować state.

W CI dozwolone są deterministic fixtures.

Nie robić production dual-execution dla kosztownych/external side effects.

## 10.14 Testy v110

```text
test_context_coordinator_contract.py
test_cognitive_frame_builder_contract.py
test_memory_coordinator_truth_boundary.py
test_affect_coordinator_role_boundary.py
test_dialogue_router_contract.py
test_response_plan_truth_constraints.py
test_validation_pipeline.py
test_recovery_policy.py
test_persistence_coordinator_atomicity.py
test_turn_orchestrator_parity.py
test_turn_orchestrator_failure_matrix.py
test_engine_facade_delegation.py
```

Parity families:

- route/intent;
- required components;
- memory-use decision;
- source/provenance;
- truth outcome;
- external capability request;
- repair/fallback;
- final contract;
- settlement.

Exact final text parity tylko dla protocol/deterministic routes.

## 10.15 Rollback v110

Release może utrzymywać explicit operator flag:

```text
JAZN_TURN_PIPELINE=canonical
JAZN_TURN_PIPELINE=legacy_compat
```

ale:

- default po release = canonical;
- brak automatic failover na legacy;
- legacy mode jest rollback/diagnostic, nie silent fallback;
- każda legacy_compat tura jest oznaczona w diagnostics;
- flag ma deadline usunięcia w v111.

## 10.16 Exit gate v110

```text
JaznEngine owns service construction                  NO
JaznEngine owns finalization                          NO
JaznEngine owns detailed turn pipeline                NO
TurnOrchestrator canonical path                       YES
context/memory/affect/routing ports                   typed
RecoveryPolicy single owner                           YES
automatic legacy fallback                             0
successful-turn contract parity                       PASS
failure matrix                                        PASS
turn settlement atomicity                             PASS
v108/v109 gates                                       PASS
Windows/Linux + Pyright + package/release             PASS
```

---

# 11. v111 — Canonical ConversationRunner + TurnStateMachine + Legacy Dialogue Cutover

**Target:** `16.3.25.5.111-conversation-runner-legacy-dialogue-cutover-convergence`

## 11.1 Cel

Zakończyć migrację outer conversation runtime:

- wdrożyć `ConversationRunner`;
- wdrożyć canonical `TurnStateMachine`;
- podłączyć wszystkie conversation entrypoints do jednego runnera;
- ograniczyć `JaznRuntimeSession` / `JaznEngine` do compatibility adapters lub
  usunąć z canonical callers;
- przestać opierać zwykłą rozmowę na dużych hard-coded paragraph branches
  `conversation.py`;
- usunąć `legacy_compat` pipeline po soak.

## 11.2 ConversationRunner

Planowany moduł:

`latka_jazn/core/conversation_runner.py`

Interfejs zgodny z istniejącym parent planem:

```python
class ConversationRunner:
    def submit_turn(self, request: TurnRequest) -> TurnHandle: ...
    def poll_turn(self, handle: TurnHandle) -> TurnSnapshot: ...
    def resume_turn(self, resume: ResumeRequest) -> TurnSnapshot: ...
    def finalize_turn(self, request: FinalizeRequest) -> TurnSnapshot: ...
```

Runner:

- posiada session/turn state machine;
- nie posiada model-specific semantics;
- używa `TurnOrchestrator`;
- używa `FinalizationService`;
- utrzymuje exact one logical turn;
- obsługuje polling/resume bez replayu.

## 11.3 MCP mapping

Modern MCP 2026-07-28:

```text
jazn_generate_visible_reply
→ ConversationRunner.submit_turn

durable task / pending
→ TurnHandle

jazn_status / task poll
→ ConversationRunner.poll_turn

jazn_resume_visible_reply
→ ConversationRunner.resume_turn

jazn_finalize_reply
→ ConversationRunner.finalize_turn
```

Remote task handle nie jest drugim ownerem; wskazuje istniejącą turę.

Task handle wolno zwrócić dopiero, gdy pending-turn state jest durable/readable.

## 11.4 Provider adapters

Wszystkie:

```text
ChatGPTHostAdapter
OllamaAdapter
OpenAIResponsesAdapter
OpenAICompatibleAdapter
Null/diagnostic provider
```

implementują wspólny contract.

Provider nie zapisuje:

- session truth;
- identity;
- MEMORY;
- accepted turn;
- fallback ownership.

## 11.5 Public entrypoints

Każdy publiczny conversation mode:

```text
run.py
run.py chat
run.py chat-gpt
run.py chat-ollama
run.py chat-open-ai / compatible
remote MCP
```

dochodzi do jednego `ConversationRunner`.

Alias może zmienić adapter/config, nie pętlę tury.

## 11.6 JaznRuntimeSession migration

Opcje finalne:

A. zachować jako cienki adapter do `ConversationRunner`, jeżeli publiczne testy
lub embedders nadal go wymagają;

B. usunąć po pełnym caller inventory i compatibility window.

Nie usuwać w ciemno.

## 11.7 JaznEngine final state

Definition of Done:

```text
JaznEngine = thin compatibility facade
OR
no canonical caller requires JaznEngine
```

Nie ustalać arbitralnie limitu linii jako jedynego gate. Ważniejsze:

- zero lifecycle ownership;
- zero session ownership;
- zero finalization ownership;
- zero duplicated routing ownership;
- jawne dependencies.

## 11.8 conversation.py migration

Najpierw inventory każdej branch/response family:

```text
PROTOCOL_TEXT
SAFETY_TRUTH_TEXT
STRUCTURED_HANDLER_CANDIDATE
MODEL_NLG_CANDIDATE
COMPATIBILITY_ONLY
DEAD_UNREACHABLE
```

### Zachować deterministic text

Tylko tam, gdzie wynik ma być protokołowy:

- technical diagnostic;
- truth boundary;
- safety refusal;
- exact status;
- recovery instruction.

### Migrować ordinary conversation

```text
hard-coded phrase/paragraph
→ structured route evidence
→ ResponsePlan
→ model/runtime NLG
```

Nie usuwać branch przed:

- route reachability proof;
- parity/behavioral corpus;
- no new blind route;
- soak.

## 11.9 Dead-route removal

Po v108 RouteGraphAudit mamy evidence.

v111 usuwa:

- nieosiągalne handlery;
- superseded compatibility branches;
- duplicate route owners;
- stare fallback strings;
- legacy pipeline flag;
- unused construction paths.

Każde usunięcie ma:

- caller search;
- test evidence;
- archive snapshot, jeśli aktywny historyczny test jest modyfikowany zgodnie z
  repo policy.

## 11.10 Retry/recovery ownership

Finalna zasada:

```text
transport retry/poll          MCP/client transport layer
provider retry                provider adapter, bounded
turn repair                   RecoveryPolicy
host resume                   ConversationRunner
daemon restart                runtime supervisor
```

Ta sama awaria nie może być retry'owana na wszystkich poziomach.

Provider retry:

- bounded attempt count;
- exponential backoff + jitter dla network/transient failure;
- no retry dla contract/lineage failures;
- retry diagnostics zachowane w tej samej turze.

## 11.11 Graceful degradation

Przykładowa matryca:

| Awaria | Dozwolone zachowanie |
|---|---|
| optional project index unavailable | continue only on routes that do not require it |
| autobiographical MEMORY unavailable | ordinary dialogue allowed, autobiographical claim blocked/abstain |
| local model unavailable, verified host-model channel exists | `EXTERNAL_CAPABILITY_REQUIRED` |
| optional affect projection unavailable | explicit degraded/advisory state if route remains truthful |
| route unresolved | terminal or bounded generic dynamic route only if truth requirements are satisfiable |
| lineage/finalization mismatch | `TERMINAL_DIAGNOSTIC` |
| persistence failure before acceptance | no accepted visible commit |
| remote transport lost after durable submit | poll/resume same request, never replay user message |

## 11.12 Testy v111

```text
test_conversation_runner_single_owner.py
test_turn_state_machine_transitions.py
test_turn_state_machine_illegal_transitions.py
test_runner_idempotent_submit.py
test_runner_poll_resume_no_replay.py
test_runner_finalize_exactly_once.py
test_mcp_task_durable_before_handle.py
test_provider_adapter_parity.py
test_public_entrypoint_single_runner.py
test_runtime_session_compat_adapter.py
test_conversation_legacy_inventory.py
test_conversation_structured_response_migration.py
test_no_legacy_auto_fallback.py
test_retry_ownership.py
test_graceful_degradation_matrix.py
test_remote_disconnect_resume.py
```

## 11.13 Soak v111

Minimum soak evidence:

- deterministic full suite;
- repeated daemon restart;
- request replay attempts;
- remote disconnect after submit;
- remote disconnect before finalization;
- model unavailable/recovered;
- memory unavailable/recovered;
- tool failure;
- validator repair;
- concurrent two sessions;
- duplicate finalize;
- cancelled/expired task.

## 11.14 Exit gate v111

```text
ConversationRunner canonical owner                    YES
TurnStateMachine canonical                            YES
all conversation entrypoints use one runner           YES
provider owns session truth                           NO
automatic legacy engine fallback                      0
legacy_compat pipeline flag                           REMOVED
anonymous fallbacks                                   0
blind active routes                                   0
duplicate canonical route owners                      0
phase2 full-engine construction                       0
constructor persistent side effects                   0
ordinary hard-coded paragraph routing                 materially removed
MCP submit/poll/resume/finalize no replay             PASS
accepted final exactly once                           PASS
crash/restart durability                              PASS
Windows/Linux                                         PASS
Pyright                                               PASS
package cleanroom/release-hardening                   PASS
real host E2E                                         external evidence required
```

---

# 12. Pliki planowane w programie

To jest proponowana mapa; exact file split może być skorygowany po fresh-master
inventory każdego release.

```text
latka_jazn/core/
├── turn_diagnostics.py             # v108
├── failure_taxonomy.py             # v108, jeśli osobny plik uzasadniony
├── blind_route_detector.py         # v108
├── route_graph_contract.py         # v108
├── engine_services.py              # v108/v109
├── runtime_composition.py          # v109
├── finalization_service.py         # v109
├── turn_orchestrator.py            # v110
├── context_coordinator.py          # v110
├── cognitive_frame_builder.py      # v110
├── memory_coordinator.py           # v110
├── affect_coordinator.py           # v110
├── dialogue_router.py              # v110
├── response_pipeline.py            # v110
├── validation_pipeline.py          # v110
├── recovery_policy.py              # v110
├── persistence_coordinator.py      # v110
├── conversation_runner.py          # v111
└── turn_state_machine.py           # v111

latka_jazn/tools/
└── route_graph_audit.py            # v108
```

Nie tworzyć pliku tylko dla nazwy. Jeśli dwa komponenty są małe i mają jeden
owner, mogą być jednym modułem.

---

# 13. Kontrakty wejścia/wyjścia

## TurnRequest

```python
@dataclass(frozen=True, slots=True)
class TurnRequest:
    session_id: str
    request_id: str
    user_text: str
    client_kind: str
    capability_snapshot: Mapping[str, JsonValue]
    deadline_utc: str | None
    metadata: Mapping[str, JsonValue]
```

`user_text` pozostaje w runtime input. Nie jest automatycznie kopiowany do
telemetry.

## TurnHandle

```python
@dataclass(frozen=True, slots=True)
class TurnHandle:
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    state: str
    revision: int
```

## TurnSnapshot

```text
state
attempt
pending external requirements
diagnostic summary
finalization eligibility
accepted-visible metadata if accepted
```

## ResponsePlan

```text
required_points
evidence_refs
forbidden_claims
source constraints
model/tool requirements
presentation intent
```

## TurnResult

Nie mieszać:

```text
runtime outcome
host action
visible text
diagnostics
```

w jedno niejawne pole.

---

# 14. Privacy / security diagnostics policy

## Do telemetry wolno

- turn/request/trace IDs;
- component/stage;
- reason codes;
- exception type;
- bounded non-sensitive error description;
- latency;
- counts;
- route/handler symbolic names;
- version/schema;
- capability class;
- source class bez private content.

## Domyślnie nie wolno

- raw user text;
- full prompts;
- MEMORY excerpts;
- journal;
- relationship/private profile content;
- auth headers/tokens;
- filesystem secrets;
- full tool arguments, jeśli mogą zawierać dane prywatne;
- W3C `tracestate` z PII.

Stacktrace pozostaje lokalnym diagnostic evidence i wymaga redaction policy,
jeśli ma być eksportowany.

---

# 15. Error ID dla użytkownika

Każda terminalna lub istotna degraded odpowiedź może pokazać bounded ID:

```text
JAZN-TURN-<short-id>
```

Użytkownik widzi np.:

> Nie udało się domknąć tej trasy: zatrzymała się na etapie pamięci. Nie będę
> zgadywać. Kod diagnostyczny: `JAZN-TURN-7F31...`.

Pełne dane są w local diagnostics:

```text
turn_id
trace_id
stage
component
reason
route lineage
fallback lineage
repair attempts
validator outcome
finalization state
```

---

# 16. CLI / diagnostics

Po v108/v111 przewidzieć:

```text
run.py diagnostics turn --turn-id <id> --json
run.py diagnostics request --request-id <id> --json
run.py diagnostics failures --recent 20 --json
run.py audit routes --json
```

Exact naming należy dopasować do istniejącego `latka_jazn.cli`, bez tworzenia
drugiego parsera.

---

# 17. CI strategy

## 17.1 Fast contract lane

Na każdy push:

- compileall;
- targeted unit;
- route graph audit;
- anonymous fallback audit;
- diagnostic schema tests;
- Pyright targeted.

## 17.2 Full deterministic lane

- `pytest -m "not live_model and not live_mcp"`;
- failure injection;
- parity corpus;
- atomicity;
- restart/recovery;
- package smoke.

## 17.3 Cross-platform lane

Windows + Linux:

- daemon;
- persistent runtime;
- path/encoding;
- SQLite/thread/process boundaries;
- public entrypoints.

## 17.4 Release lane

- metadata sync;
- integrity/provenance;
- package cleanroom;
- release-build;
- deployment contract;
- no private files.

## 17.5 External acceptance lane

Nie udawać CI:

- real ChatGPT app capability;
- public HTTPS deployment;
- OAuth;
- real tunnel loss;
- host accepted `display_exact`.

Status: `EXTERNAL_EVIDENCE_REQUIRED` do czasu realnego testu.

---

# 18. Performance gates

Najpierw baseline, potem thresholds.

Mierzyć:

```text
turn total p50/p95
context p50/p95
memory p50/p95
routing p50/p95
validation p50/p95
finalization p50/p95
diagnostics overhead
startup/hydrate time
memory allocations if measurable
```

Cel v108: diagnostics overhead ma być mierzalny i bounded.

Nie ustalać arbitralnie np. "p95 < 100 ms", zanim nie ma baseline dla realnych
ścieżek.

---

# 19. Code-health gates

Mierzyć trend:

```text
engine.py bytes/lines
JaznEngine.__init__ size
JaznEngine.process_turn size
constructor side-effect count
number of service dependencies constructed inside engine
anonymous fallback count
unreachable handler count
duplicate route owner count
finalization dependency count
legacy conversation branch count
structured response plan coverage
```

Nie zaliczać refactoru przez przeniesienie tego samego monolitu do jednego
nowego helpera.

---

# 20. Release discipline

Każdy implementation release:

1. fresh `master`;
2. branch z jednym zakresem;
3. checkpoint;
4. characterization before behavior move;
5. implementation;
6. targeted tests;
7. full deterministic suite;
8. cross-platform CI;
9. version bump w tym samym patchu;
10. canonical metadata sync;
11. package/release smoke;
12. PR jako draft do czasu finalnego HEAD i zielonych gates;
13. merge dopiero po świadomym review.

Nie edytować ręcznie:

- `PACKAGE_INTEGRITY_MANIFEST.json`;
- `SOURCE_PROVENANCE.json`.

---

# 21. Branch / PR plan

Nazwy orientacyjne:

```text
upgrade/v16.3.25.5.108-engine-decomposition-turn-diagnostics-convergence
upgrade/v16.3.25.5.109-engine-lifecycle-finalization-decomposition-convergence
upgrade/v16.3.25.5.110-turn-orchestrator-engine-decomposition-convergence
upgrade/v16.3.25.5.111-conversation-runner-legacy-dialogue-cutover-convergence
```

Jeśli przed startem danego etapu `master` ma już wyższy legalny numer, zachować
kolejność logiczną milestone'ów, a nie wymuszać kolizję numeru.

---

# 22. Rollback strategy

## v108

Wyłączyć export/persistence diagnostics; nie zmieniać runtime behavior.

## v109

Cofnąć release do poprzedniego commita. Nie robić runtime auto-fallback z nowej
finalizacji do starej po błędzie.

## v110

Jawny `legacy_compat` operator mode przez jeden release, bez auto failover.
Każde użycie raportowane.

## v111

Po soak usunąć legacy mode. Rollback = poprzedni release/image/commit, nie
dynamiczne przełączanie jednej tury między dwoma owners.

---

# 23. Failure-injection master matrix

| Failure | Expected owner | Expected result |
|---|---|---|
| malformed input | ingress | terminal typed diagnostic |
| duplicate request | runner/idempotency | return same logical turn |
| memory offline | MemoryCoordinator | abstain/degrade according to route |
| handler exception | DialogueRouter/RecoveryPolicy | typed fallback or terminal |
| local model offline | provider/RecoveryPolicy | external capability or terminal |
| tool unavailable | RecoveryPolicy | explicit capability required |
| validator rejects | ValidationPipeline | repair attempt or terminal |
| repair rejects | RecoveryPolicy | terminal |
| finalization stale | FinalizationService | terminal, no commit |
| duplicate finalize | FinalizationService | idempotent same accepted final or reject conflicting |
| persistence fails | PersistenceCoordinator | no accepted durable state |
| daemon killed | supervisor | recover runtime, do not replay turn |
| tunnel lost | transport | local runtime stays alive; poll/resume later |
| worker timeout | runner/timeout owner | bounded terminal/cancel state |
| process restart | runner stores | recover pending/accepted state |
| concurrent same session | TurnStateMachine/session owner | deterministic serialization/conflict policy |

---

# 24. Definition of Done v108–v111

Program jest zakończony dopiero, gdy:

```text
[ ] one canonical ConversationRunner
[ ] one canonical TurnStateMachine
[ ] one TurnDiagnosticTrace per logical turn
[ ] every important fallback typed
[ ] no anonymous fallback in active critical paths
[ ] no unexplained blind routes
[ ] one RecoveryPolicy owner
[ ] JaznEngine constructor side-effect free
[ ] phase2 finalization independent of full engine
[ ] JaznEngine is thin facade or absent from canonical callers
[ ] public conversation entrypoints share one runner
[ ] provider adapters do not own session/memory/identity/finalization
[ ] no automatic legacy failover after canonical switch
[ ] ordinary dialogue is structurally planned, not dominated by phrase→paragraph legacy
[ ] repair attempts preserve original failure evidence
[ ] accepted final exactly once
[ ] no message replay on ambiguous transport
[ ] MCP durable task maps to existing logical turn
[ ] MEMORY truth boundary unchanged
[ ] Affect authority unchanged unless its own plan changes it
[ ] diagnostics privacy contract PASS
[ ] deterministic failure injection PASS
[ ] Windows/Linux PASS
[ ] Pyright PASS
[ ] package/release hardening PASS
[ ] real host E2E recorded separately from repository CI
```

---

# 25. Najważniejsza zasada implementacyjna

Nie zaczynać v108 od masowego przenoszenia kodu.

Najpierw:

```text
observe
→ classify
→ characterize
→ build trace
→ prove route graph
→ create seams
```

Dopiero potem:

```text
extract
→ shadow/parity
→ switch
→ soak
→ remove
```

Dzięki temu każda późniejsza regresja ma odpowiedź:

```text
gdzie?
w której turze?
w jakim komponencie?
z jakiej trasy?
z jakim reason code?
czy był repair?
czy fallback był legalny?
czy finalizacja została zaakceptowana?
```

To jest warunek bezpiecznego przeprogramowania `JaznEngine`, a nie dodatkowy
logging feature.


---

# 26. Completion record — 2026-10-06

The v108→v111 implementation program is complete on the stacked, unmerged series
#318–#321. Final v111 SHA:
`ee00529cdbd9a4d0a469007db787ed4895667ddf`.

Repository exit evidence: **2107 PASS / 4 platform SKIPPED / 0 FAIL** locally,
plus terminal SUCCESS for Pyright, release-hardening, persistent-runtime E2E on
Linux/Windows, package cleanroom and PowerShell.

The previously external real-host gate was then executed on a real ChatGPT host
using the final GitHub Actions v111 system artifact. The local-executor route
materialized and started the verified runtime, bound one user message to one durable
request, rejected an incorrect phase-2 binding fail-closed without replay, resumed
the same request and produced an accepted finalization with
`accepted_visible_turn_ready=true`, `action=display_exact`, and a valid
turn-authority receipt.

This completion does **not** promote the separately unverified public/secure remote
MCP deployment route and does not authorize merging any PR.
