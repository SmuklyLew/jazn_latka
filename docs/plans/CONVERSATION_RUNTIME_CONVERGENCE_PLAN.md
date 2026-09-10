# Jaźń — plan konwergencji systemu rozmowy

**Status:** `ACTIVE_IMPLEMENTATION_PLAN`
**Data:** 2026-09-10
**Cel:** jeden profesjonalny runtime rozmowy niezależny od dostawcy LLM
**Baza:** `master @ 74bc67437702dd07488e4e7f07893d1a7fec1dd7`, v58
**Pierwszy etap:** v59 `conversation-runtime-orchestration-convergence`

## 1. Definicja celu

Po migracji użytkownik zawsze rozpoczyna turę w Jaźni. ChatGPT, OpenAI Responses, Ollama i przyszłe backendy są wymiennymi wykonawcami języka/narzędzi. Żaden provider nie jest właścicielem pamięci, tożsamości, session state, permission state, accepted-turn lineage ani finalizacji.

Docelowy przepływ:

```text
run.py chat
    │
    ▼
ConversationRunner
    │
    ├─ IngressNormalizer / exact input fingerprint
    ├─ SessionStateOwner
    ├─ TurnStateMachine
    ├─ ContextBuilder
    │    ├─ working/session history
    │    ├─ memory retrieval + provenance
    │    ├─ affect/self-state projection
    │    └─ policy/tool availability
    ├─ ModelRouter
    │    ├─ ChatGPTHostAdapter
    │    ├─ OpenAIResponsesAdapter
    │    ├─ OllamaAdapter
    │    └─ OpenAICompatibleAdapter
    ├─ ToolLoop
    ├─ FinalizationGate
    ├─ PresentationEnvelope
    └─ Event/Trace/Persistence commit
```

Publiczne aliasy pozostają przez okres zgodności:

```text
run.py chat-gpt    -> chat --backend chatgpt-host
run.py chat-ollama -> chat --backend ollama
chat-open-ai       -> chat --backend openai-api
```

Alias nie może implementować własnej pętli tury.

## 2. Niezmienniki architektury

### INV-01 — single turn owner
Dla jednego `turn_id` istnieje dokładnie jeden runtime owner. Daemon albo jawny dozwolony one-shot jest ownerem; host/model nigdy nim nie jest.

### INV-02 — single session owner
Kanoniczna historia sesji należy do Jaźni. Provider-specific continuation IDs są tylko metadanymi adaptera.

### INV-03 — one input fingerprint → one logical turn
`session_id + normalized/exact user input hash + client request/idempotency key` nie może utworzyć dwóch aktywnych logicznych tur przy retry transportu.

### INV-04 — at most one accepted visible final
Tura może mieć wiele kandydatów/retry, ale co najwyżej jeden zaakceptowany `final_visible_text` dla danej revision.

### INV-05 — no visible bypass
Tekst przypisany runtime musi mieć świeże `turn_id`, `trace_id`, input hash i zaakceptowaną finalizację. Brak dowodu → host diagnostic.

### INV-06 — tool side effects are idempotent
Każdy tool call ma stabilny `tool_call_id` i idempotency key. Resume/replay nie wykonuje drugi raz operacji już zatwierdzonej i zapisanej.

### INV-07 — header belongs to finalizer
Model i host nie są właścicielem nagłówka Łatki. Runtime formatter/finalizer tworzy lub waliduje finalny envelope.

### INV-08 — persistence precedes acknowledgement where required
Stan, którego utrata spowodowałaby powtórzenie skutku lub podwójny final, musi być zapisany przed potwierdzeniem przejścia do następnej fazy.

## 3. Docelowa maszyna stanów tury

```text
RECEIVED
  ↓
ADMITTED
  ↓
CONTEXT_READY
  ↓
MODEL_PENDING
  ├──────────────→ MODEL_RESULT_READY
  │                    │
  │                    ├─ tool calls → TOOL_PENDING
  │                    │                ↓
  │                    │             TOOL_RESULT_READY
  │                    │                └──→ MODEL_PENDING
  │                    │
  │                    └─ host wording required → HOST_GENERATION_PENDING
  │                                              ↓
  │                                      HOST_CANDIDATE_READY
  │
  └──────────────────────────────────────────────┘
                         ↓
                 FINALIZATION_PENDING
                         ↓
                     FINALIZED
                         ↓
                   VISIBLE_COMMITTED
```

Stany terminalne błędu:

```text
REJECTED
TIMED_OUT
CANCELLED
INDETERMINATE
HOST_FINALIZATION_EXPIRED
PROVIDER_UNAVAILABLE
```

Każda tranzycja ma co najmniej:
- `session_id`
- `turn_id`
- `trace_id`
- `revision`
- `event_seq`
- `input_sha256`
- `state_before`
- `state_after`
- `timestamp`
- `owner`
- opcjonalne provider/tool IDs
- reason/error_code

## 4. Trzy oddzielne reprezentacje rozmowy

Nie wolno utrzymywać jednej listy `messages` jako uniwersalnego źródła wszystkiego.

### 4.1 Canonical runtime event/history view
Pełna historia user/runtime/tool/policy/finalization z lineage i provenance. To źródło audit, resume i memory projection.

### 4.2 Provider input/replay view
Minimalna projekcja potrzebna wybranemu adapterowi. Może zawierać provider IDs, tool schemas, skompaktowaną historię i różne formaty per provider. Nie jest kanoniczną pamięcią Jaźni.

### 4.3 User-visible presentation view
Wyłącznie zaakceptowany tekst/structured output po truth/finalization gate. Brak surowych tool traces, provider internals i niezatwierdzonych kandydatów.

## 5. Kontrakt `ConversationRunner`

Minimalny interfejs docelowy:

```python
class ConversationRunner:
    def submit_turn(self, request: TurnRequest) -> TurnHandle: ...
    def poll_turn(self, handle: TurnHandle) -> TurnSnapshot: ...
    def resume_turn(self, resume: ResumeRequest) -> TurnSnapshot: ...
    def cancel_turn(self, handle: TurnHandle) -> TurnSnapshot: ...
    def finalize_external_candidate(self, request: FinalizeRequest) -> TurnSnapshot: ...
```

`TurnRequest` zawiera exact user text, session identity, client/channel, requested backend policy i host capability attestations. Nie zawiera gotowego tekstu odpowiedzi hosta.

`TurnSnapshot` jest action-first i może żądać:
- `display_exact`
- `wait/poll`
- `execute_tool`
- `external_generation_required`
- `approval_required`
- `host_diagnostic`

## 6. ModelRouter i adaptery

Wspólny kontrakt adaptera:

```python
class ModelAdapter:
    def probe(self) -> ModelCapabilitySnapshot: ...
    def generate(self, request: ModelRequest) -> ModelResult: ...
    def cancel(self, request_id: str) -> None: ...
```

Każdy adapter deklaruje capabilities: tools, streaming, structured output, vision, thinking/reasoning controls, server continuation, cancellation.

### Auto-routing

Kanoniczna kolejność v59:

```text
confirmed ChatGPT host
→ usable local Ollama
→ explicitly allowed paid OpenAI API
→ null fallback
```

Kolejność jest jednym kontraktem importowanym przez resolver, discovery i help. Runtime musi emitować `selected_route`, `reason` i evidence.

## 7. ChatGPT Host Adapter

`ChatGPTHostAdapter` jest szczególny, bo model żyje poza procesem Python.

### Phase 1
Runtime wykonuje ingest, memory/context/policy i zwraca action-first packet z:
- `turn_id`
- `trace_id`
- input hash
- generation context
- bounded instructions/context
- pending-request identity
- expiry/continuation contract

### Phase 2
Host generuje kandydat, ale nie pokazuje go użytkownikowi. Kandydat wraca przez `host-finalize`/MCP. Runtime:
- claimuje dokładny pending request;
- waliduje hash i lineage;
- ocenia response candidate;
- tworzy nagłówek/envelope;
- wykonuje final commit;
- dopiero wtedy zwraca `display_exact`.

### Krytyczna granica produktu ChatGPT
Kod repo nie może wymusić wywołania narzędzia przez produkt ChatGPT. Dlatego docelowo potrzebne jest host-side MCP/ChatGPT App API:

```text
jazn_turn(exact_user_message, session_binding)
jazn_resume(turn_id, continuation)
jazn_finalize(turn_id, candidate, candidate_sha256)
```

Najlepiej, aby `jazn_turn` był jedynym narzędziem wejścia dla rozmowy z Jaźnią, a pozostałe operacje były zwracanymi continuation actions lub wewnętrznym adapterem.

## 8. ToolLoop

Runtime, nie model, jest właścicielem wykonania narzędzi.

Przepływ:
1. adapter zwraca typed tool calls;
2. runtime mapuje canonical tool identity;
3. policy/permission/guardrail gate;
4. wymagane approval → trwałe `APPROVAL_PENDING`;
5. wykonanie z timeout/cancellation;
6. atomic record `{tool_call_id, args_hash, result_hash, status}`;
7. sanitized provider result;
8. kolejny model iteration.

Retry po restarcie sprawdza zapisany status i nie powtarza zaakceptowanego side effectu.

## 9. Lifecycle events / hooks

Wprowadzić typed events, inspirowane dojrzałymi agent runtimes:

```text
SESSION_START
TURN_RECEIVED
BEFORE_CONTEXT
AFTER_CONTEXT
BEFORE_MODEL
AFTER_MODEL
BEFORE_TOOL_SELECTION
BEFORE_TOOL
AFTER_TOOL
BEFORE_FINALIZATION
AFTER_FINALIZATION
TURN_COMMITTED
SESSION_END
```

Hook nie może dowolnie modyfikować wszystkich struktur. Każdy event ma określony input/output contract i allowed decisions (`observe`, `augment`, `allow`, `deny`, `retry`). Affect/memory/policy integrują się przez te punkty.

## 10. Observability

Każda tura ma jeden trace root. Minimalne spany:
- ingress
- session acquire
- memory retrieval
- context build
- route selection
- provider/model call
- each tool call
- host external generation wait
- finalization
- persistence
- presentation commit

Metryki:
- latency p50/p95/p99 per stage;
- active/pending turns;
- retries and cancellations;
- provider selection/fallback;
- host routing bypass count;
- duplicate request prevented count;
- tool replay prevented count;
- resume success rate;
- finalization rejected/expired count;
- session restore success;
- memory retrieval coverage/provenance failures.

Raw private content nie trafia do telemetry domyślnie.

## 11. Plan migracji etapami

### Etap 0 — v59: kontrakt i drift elimination
**Implementowany w bieżącym patchu.**

- jeden `conversation_entrypoint_contract`;
- jedna deklaracja auto-route priority;
- discovery rozróżnia universal `conversation` od legacy `local_chat`;
- runtime environment używa wspólnych command constants;
- CLI help nie opisuje błędnej kolejności routingu;
- runbook/Project loader wymagają świeżej tury runtime przed każdą zwykłą odpowiedzią hosta ChatGPT;
- testy kontraktowe i wersja v59.

**Exit gate:** brak dryfu route semantics, loader ≤ 5000 znaków, regression tests green.

### Etap 1 — wydzielenie `ConversationRunner`
- utworzyć `latka_jazn/core/conversation_runner.py`;
- przenieść orchestration helpers z `main.py`, bez zmiany behavior;
- `run.py/cli.py` kompozycja, `main.py` shim;
- compatibility snapshot tests.

**Exit gate:** stare i nowe wejścia produkują równoważny canonical turn contract.

### Etap 2 — single daemon/session execution owner
- skierować `run.py chat` one-shot i TTY przez ten sam runtime execution service co `chat-gpt`;
- usunąć sytuację, w której `chat` tylko sprawdza daemon, a następnie tworzy niezależny lokalny worker;
- jawny fallback one-shot tylko gdy policy na niego zezwala i z innym ownership state.

**Exit gate:** jedna sesja, 100+ tur, brak podwójnych worker owners; restart daemonu zachowuje kolejność i state lineage.

### Etap 3 — unified provider adapter boundary
- wszystkie backendy przez `ModelAdapter` + capability snapshot;
- `chat-gpt`, Ollama, OpenAI API jako selectors/aliases;
- przygotować generic OpenAI-compatible adapter dla lokalnych serwerów bez zmiany ownership.

**Exit gate:** zmiana providera między turami nie traci session identity i nie zmienia memory owner.

### Etap 4 — persisted TurnStateMachine
- trwały event log tury;
- revision/event_seq;
- state transition validation;
- atomic persistence przed acknowledgement;
- crash/restart recovery.

**Exit gate:** property/state-machine tests + kill/restart tests na każdej pending phase.

### Etap 5 — runtime-owned ToolLoop
- canonical tool identity;
- approval/permission gate;
- idempotency ledger;
- cancellation/timeouts;
- tool result projection do providerów.

**Exit gate:** retries/resume nie powtarzają side effect; każdy tool task terminalizuje deterministycznie.

### Etap 6 — typed lifecycle events
- memory, affect, policy i observability podłączone do eventów;
- bez bocznych provider-specific hooków w `main.py`.

**Exit gate:** ablation potwierdza, że wyłączenie modułu usuwa tylko jego bounded effect.

### Etap 7 — ChatGPT MCP/App hard gate
- `jazn_turn` + resume/finalize contract;
- exact input binding;
- per-turn host attestations;
- produktowy test wieloturowy;
- host bypass telemetry.

**Exit gate:** 10/10 kolejnych tur w prawdziwym hoście mają świeże runtime lineage; jedna goła odpowiedź hosta = FAIL.

### Etap 8 — streaming/cancellation parity
- stream events jako widok, nie drugi state owner;
- stream i non-stream identyczne semantycznie;
- cancellation propaguje się do provider/tool, a stan kończy deterministycznie.

### Etap 9 — legacy removal
- usunąć direct mature conversation implementation z `main.py` dopiero po okresie kompatybilności;
- zostawić jawny shim/deprecation diagnostic;
- usunąć aliases dopiero po usage evidence i migration notes.

## 12. Zmiany powiązanych części systemu

Przebudowa rozmowy wymaga kontroli również:
- runtime daemon/session worker ownership;
- memory context projection i provenance;
- affect/self-state hooks;
- permission/tool registry;
- final response contract/header;
- audit/decision ledger;
- clock/timestamp provenance;
- MCP gateway;
- package/release metadata;
- docs/runbooks;
- CI cross-platform Windows/Linux.

Nie należy jednak łączyć ich w jeden gigantyczny commit. Każda faza ma własny release/version, testy, rollback i evidence.

## 13. Rollback

Każdy etap zachowuje publiczne wejścia do czasu przejścia acceptance gate. Migracja jest add-then-switch-then-remove:

```text
new component present
→ shadow/contract parity
→ canonical switch
→ soak/E2E
→ legacy deprecated
→ legacy removed in later release
```

Nigdy: rename/remove przed dowodem równoważności.

## 14. Definition of Done całej przebudowy

Przebudowa jest zakończona dopiero gdy:
- `run.py chat` jest jedynym canonical conversation orchestration entry;
- daemon/runtime jest jedynym session/turn owner w persistent mode;
- wszystkie modele są adapterami;
- tool loop jest runtime-owned i idempotentny;
- każda pending phase przeżywa restart albo kończy się jawnie fail-closed;
- ChatGPT host E2E nie potrafi wyświetlić runtime-attributed tekstu bez świeżego turn lineage;
- header/final envelope pochodzi wyłącznie z finalizer;
- streaming i non-stream mają parity;
- `main.py` nie posiada konkurencyjnego canonical flow;
- pełne testy Windows/Linux, package smoke, doctor i release hardening przechodzą;
- dokumentacja odpowiada rzeczywistemu dispatchowi.
