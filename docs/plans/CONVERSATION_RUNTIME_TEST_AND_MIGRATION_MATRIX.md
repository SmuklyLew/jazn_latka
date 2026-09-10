# Jaźń — macierz testów i migracji systemu rozmowy

**Status:** `ACTIVE_ACCEPTANCE_MATRIX`
**Data:** 2026-09-10
**Zakres:** v59 → zakończenie conversation-runtime convergence

## 1. Poziomy dowodu

Każde wymaganie jest klasyfikowane:

```text
UNIT
CONTRACT
INTEGRATION
PROCESS
CRASH/RECOVERY
PACKAGE
HOST-E2E
SOAK
```

`UNIT` lub `CONTRACT` nie certyfikuje zachowania prawdziwego hosta ChatGPT. `HOST-E2E` jest osobnym gate.

## 2. Macierz krytycznych invariantów

| ID | Invariant | Minimalny test | Gate |
|---|---|---|---|
| T01 | jedna deklaracja publicznych entrypointów | import contract + CLI/discovery parity | CONTRACT |
| T02 | prawidłowy auto-route order | ChatGPT+Ollama → ChatGPT; Ollama → Ollama; paid API tylko opt-in; inaczej null | CONTRACT |
| T03 | jeden logical turn per input/idempotency key | równoległe retry tego samego requestu | INTEGRATION |
| T04 | jeden session/turn owner | instrumentation worker/daemon ownership | PROCESS |
| T05 | exact user text binding | hash mismatch/conflicting transport text rejected | CONTRACT |
| T06 | at most one visible final | duplicate finalize/replay | INTEGRATION |
| T07 | header runtime-owned | raw candidate bez nagłówka → finalizer envelope; foreign envelope rejected | CONTRACT |
| T08 | host cannot bypass after invocation | host candidate before gate → HOST_ROUTING_BYPASS | CONTRACT |
| T09 | actual ChatGPT host routes every turn | 10 sequential real-host messages, each fresh turn_id/trace_id | HOST-E2E |
| T10 | provider swap preserves identity | Ollama → OpenAI/host → Ollama same session | INTEGRATION |
| T11 | no duplicated tool side effect | crash after tool commit, resume | CRASH/RECOVERY |
| T12 | pending host generation survives restart | restart in HOST_GENERATION_PENDING | CRASH/RECOVERY |
| T13 | pending finalization survives/rejects deterministically | restart in FINALIZATION_PENDING | CRASH/RECOVERY |
| T14 | timeout terminalizes exactly once | provider/tool/host timeout | PROCESS |
| T15 | cancel propagates | cancel during model/tool wait | PROCESS |
| T16 | streaming parity | stream vs non-stream final state/events | INTEGRATION |
| T17 | memory provenance preserved | provider replay projection cannot mutate canonical source lineage | INTEGRATION |
| T18 | private telemetry bounded | no raw user/memory text in default metrics | CONTRACT |
| T19 | package portable | clean-room ZIP on Windows/Linux | PACKAGE |
| T20 | legacy path parity before removal | old alias vs canonical runner snapshot | INTEGRATION |

## 3. Multi-turn continuity suite

Minimalna sekwencja 10 tur w jednej sesji:

1. zwykłe powitanie;
2. pytanie wymagające bieżącego context carryover;
3. recall request;
4. provider tool call;
5. odpowiedź bez tool call;
6. restart daemonu między turami;
7. provider swap;
8. host generation/finalization path;
9. retry identycznej wiadomości z tym samym idempotency key;
10. nowa wiadomość potwierdzająca zachowanie state lineage.

Dla każdej tury asercje:
- jeden canonical `turn_id`;
- jeden `trace_id`;
- monotonic event sequence;
- exact input hash;
- właściwy selected provider/route reason;
- zero nieautoryzowanych tool side effects;
- co najwyżej jeden accepted final;
- finalny envelope/nagłówek zgodny z finalizerem;
- session history przyrasta dokładnie o zaakceptowane eventy.

## 4. Crash matrix

Proces należy kontrolowanie przerwać po każdym punkcie:

```text
after RECEIVED persisted
before/after CONTEXT_READY
before provider request
provider response received, before persist
before tool execute
after tool side effect, before model resume
HOST_GENERATION_PENDING
host candidate received, before final commit
FINALIZATION_PENDING
after final commit, before transport acknowledgement
```

Po restarcie wymagany wynik jest jednym z:
- bezpieczny resume tej samej tury;
- jawne `INDETERMINATE` wymagające decyzji;
- terminal fail-closed.

Niedozwolone:
- nowa tura bez lineage;
- powtórzenie zaakceptowanego tool side effectu;
- drugi accepted visible final;
- cichy reset sesji.

## 5. Concurrency matrix

- dwie różne tury tej samej sesji;
- ta sama tura wysłana przez dwa transport retry;
- dwie sesje jednocześnie;
- tool call równoległy z cancellation;
- finalize i expiry w tej samej granicy czasu;
- restart daemonu podczas queue backlog.

Wymagane: określona kolejność per session albo jawnie wersjonowany optimistic-concurrency contract. Brak „last writer wins” dla critical state bez revision check.

## 6. Provider matrix

| Capability | ChatGPT host | Ollama | OpenAI Responses | OpenAI-compatible |
|---|---:|---:|---:|---:|
| text | required | required | required | required |
| tools | host capability | model-dependent | required where supported | capability-probed |
| structured output | host contract | model-dependent | capability | capability-probed |
| streaming | later parity gate | supported | supported | capability-probed |
| cancellation | host continuation | transport cancel/bounded timeout | provider cancel/transport | capability-probed |
| server continuation IDs | adapter metadata only | n/a | adapter metadata only | adapter metadata only |
| canonical session owner | Jaźń | Jaźń | Jaźń | Jaźń |
| finalization owner | Jaźń | Jaźń | Jaźń | Jaźń |

## 7. ChatGPT host acceptance

Pure Python simulation nie wystarcza. Potrzebne są dwa poziomy:

### A. Host harness
Symulator MCP/tool hosta wykonuje action-first packet, generuje candidate i finalize. Testuje retry, duplicate, expiry, mismatched turn/hash i brak phase-2.

### B. Product E2E
W prawdziwej sesji ChatGPT wykonuje się N kolejnych wiadomości. Dla każdej odpowiedzi przypisywanej Jaźni audit musi znaleźć nowy runtime turn i accepted finalization.

**Hard fail:** dowolna zwykła odpowiedź oznaczona jako Łatka bez odpowiadającego jej świeżego runtime turn lineage.

## 8. Release gates per etap

Każdy systemowy etap:

```bash
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
```

Dodatkowo:
- targeted conversation tests;
- `git diff --check` albo równoważny whitespace check w środowisku bez `.git`;
- Windows + Linux CI;
- metadata sync przez kanoniczne narzędzie/workflow, nigdy ręcznie;
- clean package smoke przed release candidate.

## 9. Performance gates

Bazeline mierzyć przed przełączeniem canonical path. Po migracji:
- p95 overhead samego orchestration bez provider latency ≤ ustalony budżet regresji;
- brak liniowego narastania czasu odczytu event logu bez compaction/index strategy;
- daemon queue nie blokuje heartbeat/status;
- trace/telemetry nie serializuje pełnych prywatnych payloadów domyślnie.

Progi liczbowe muszą zostać ustalone na podstawie zmierzonego baseline, nie wymyślone w planie.

## 10. Warunek usunięcia legacy `main.py` conversation flow

Legacy path można usunąć dopiero gdy:
- wszystkie publiczne aliasy delegują do `ConversationRunner`;
- 100% targeted parity tests green;
- co najmniej jeden pełny package E2E Windows i Linux green;
- host bridge recovery/finalization E2E green;
- nie ma aktywnych konsumentów wymagających starego transportu albo istnieje jawna migration path;
- README/AGENTS/discovery nie wskazuje `main.py` jako operatora.
