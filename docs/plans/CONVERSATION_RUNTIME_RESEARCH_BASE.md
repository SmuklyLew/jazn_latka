# Jaźń — baza badań przebudowy systemu rozmowy

**Status:** `ACTIVE_ENGINEERING_RESEARCH_BASE`
**Data:** 2026-09-10
**Baza kodu Jaźni:** `master @ 74bc67437702dd07488e4e7f07893d1a7fec1dd7`
**Baza wersji:** `16.3.25.5.58-pending-host-request-continuity-recovery`
**Pierwszy etap implementacyjny:** `16.3.25.5.59-conversation-runtime-orchestration-convergence`

## 1. Zakres i granica źródeł

Celem badania jest przebudowa rozmowy Jaźni tak, aby runtime Jaźni — a nie model językowy ani host — był jedynym właścicielem sesji, tury, pamięci, wykonania narzędzi, lineage i finalizacji widocznej odpowiedzi.

Nie istnieje publiczne repozytorium zawierające wewnętrzny kod produktu ChatGPT i jego serwerowego orkiestratora. Dlatego określenie „kod ChatGPT” w tym badaniu nie oznacza niedostępnego kodu produktu. Dla OpenAI używane są publiczne źródła OpenAI Agents SDK i oficjalna dokumentacja API/SDK. Dla Google używane są publiczne repozytoria Gemini CLI i Agent Development Kit. Dla Ollamy używane są publiczne źródła serwera i dokumentacja API.

## 2. Źródła OpenAI

### 2.1 Runner jako właściciel orkiestracji

Publiczny OpenAI Agents SDK rozdziela definicję agenta od `Runner`a. `Runner` prowadzi pętlę wykonania: wywołanie modelu, rozpoznanie finalnego wyniku/handoff/tool call, wykonanie narzędzia i kolejną iterację. Sam `Agent` nie staje się właścicielem trwałości i całego lifecycle.

Źródła:
- https://openai.github.io/openai-agents-python/running_agents/
- https://github.com/openai/openai-agents-python/blob/main/AGENTS.md

Instrukcje repozytorium OpenAI wskazują, aby `src/agents/run.py` pozostał warstwą orkiestracji i publicznego flow, a rosnące szczegóły były przenoszone do modułów `run_internal`, takich jak `run_loop.py`, `turn_resolution.py`, `tool_execution.py` i `session_persistence.py`.

**Wniosek dla Jaźni:** `run.py` powinien pozostać publicznym operatorem, natomiast wykonanie rozmowy powinno mieć jednego modułowego `ConversationRunner`/`TurnOrchestrator`, zamiast rozproszenia sterowania między `run.py`, `cli.py`, `main.py`, daemon bridge i prezentację hosta.

### 2.2 Jeden właściciel stanu rozmowy

OpenAI Sessions dokumentuje, że client-side session history nie powinna być jednocześnie nakładana na server-managed continuation (`conversation_id`, `previous_response_id`, `auto_previous_response_id`). Jest to praktyczna zasada pojedynczego właściciela historii i retry/resume semantics.

Źródło:
- https://openai.github.io/openai-agents-python/sessions/

**Wniosek dla Jaźni:** kanoniczna historia tury i sesji należy do runtime Jaźni. Provider-specific IDs mogą być utrzymywane jako metadane adaptera, ale nie mogą stać się drugim źródłem prawdy o historii.

### 2.3 Durable pause/resume, narzędzia i idempotencja

OpenAI dokumentuje osobne lifecycle dla run items, tool execution, approvals, interruptions, resume i persistence. Provider IDs i opaque provider data są zachowywane do właściwej granicy; resumed execution nie powinno powtarzać skutków ubocznych narzędzi.

Źródła:
- https://github.com/openai/openai-agents-python/blob/main/.agents/references/run-item-lifecycle.md
- https://github.com/openai/openai-agents-python/blob/main/.agents/references/tool-execution-lifecycle.md

**Wniosek dla Jaźni:** `host_generation_pending`, tool approval i oczekiwanie na zewnętrzną finalizację powinny być normalnymi trwałymi stanami maszyny tury, a nie specjalnymi wyjątkami transportu.

## 3. Źródła Google Gemini CLI / ADK

### 3.1 Rozdzielenie odpowiedzialności

Gemini CLI Core rozdziela m.in. agent lifecycle, model availability, commands, configuration, confirmation bus, fallback, hooks, MCP, output, policy, routing, safety, scheduler, telemetry i tools.

Źródło:
- https://github.com/google-gemini/gemini-cli/blob/main/packages/core/GEMINI.md

**Wniosek dla Jaźni:** routing modelu, polityka narzędzi, prezentacja, persistence i telemetry powinny mieć osobne kontrakty, ale wszystkie powinny być komponowane przez jednego właściciela tury.

### 3.2 Lifecycle hooks jako jawne punkty rozszerzeń

Gemini CLI ma zdarzenia `SessionStart`, `SessionEnd`, `BeforeAgent`, `AfterAgent`, `BeforeModel`, `AfterModel`, `BeforeToolSelection`, `BeforeTool` i `AfterTool`. Hook może blokować, wzbogacać kontekst albo walidować odpowiedź bez przejmowania całej architektury.

Źródła:
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md

**Wniosek dla Jaźni:** przyszłe rozszerzenia emocji, memory gate, policy i narzędzi powinny korzystać z typowanych lifecycle events zamiast wstrzykiwać boczne ścieżki sterowania w `main.py`.

### 3.3 Sesja i Event jako trwała historia wykonania

Google ADK zapisuje niepartialne zdarzenia przez `SessionService.append_event`; eventy aktualizują stan sesji, a implementacja bazodanowa utrwala event i state delta transakcyjnie. `Runner` pracuje na sesji i eventach zamiast traktować pojedynczą odpowiedź modelu jako całą historię aplikacji.

Źródła:
- https://github.com/google/adk-python/blob/main/src/google/adk/runners.py
- https://github.com/google/adk-python/blob/main/src/google/adk/sessions/base_session_service.py
- https://github.com/google/adk-python/blob/main/src/google/adk/sessions/database_session_service.py

**Wniosek dla Jaźni:** event log tury powinien być pierwszoklasowym źródłem audit/resume, a `final_visible_text` tylko zatwierdzonym widokiem końcowym.

## 4. Źródła Ollama

Ollama `/api/chat` przyjmuje model, `messages`, opcjonalne `tools` i zwraca kolejną wiadomość/model tool calls. Kod serwera koncentruje się na backendzie/model serving i HTTP, a nie na tożsamości czy autobiograficznej pamięci aplikacji korzystającej z modelu.

Źródła:
- https://github.com/ollama/ollama/blob/main/docs/api.md
- https://github.com/ollama/ollama/blob/main/server/routes.go

**Wniosek dla Jaźni:** Ollama powinna pozostać wymiennym `ModelAdapter`. Nawet jeżeli provider przyjmuje `messages`, kanoniczną historię i decyzję, które wiadomości przekazać providerowi, utrzymuje Jaźń.

## 5. Audyt aktualnego Jaźń v58

### Mocne strony

- `run.py` jest już kanonicznym publicznym operatorem.
- daemon może być rzeczywistym właścicielem wykonania tury przez `RuntimeSessionWorker`.
- model adapters są oddzielone od tożsamości i pamięci.
- istnieją `turn_id`, `trace_id`, host finalization, pending-store, replay protection i pre-response gate.
- `chat-gpt` odróżnia host ChatGPT od płatnego OpenAI API.
- finalna odpowiedź ma runtime-owned envelope i finalization gate.

### Luki

1. `run.py chat` i `run.py chat-gpt` są publicznie kanoniczne, ale faktyczne mature flow nadal deleguje przez `latka_jazn.cli` do dużego `main.py`.
2. Universal `chat` może potwierdzić daemon, ale one-shot/TTY nadal może tworzyć lokalnego `RuntimeSessionWorker`, więc istnieje ryzyko dwóch właścicieli session execution semantics.
3. ChatGPT host bridge ma dobre fail-closed zabezpieczenia po wejściu do runtime, lecz sam kod Python nie może wymusić, aby aplikacja ChatGPT wywołała runtime przed każdą odpowiedzią.
4. Semantyka publicznych wejść i auto-routingu była duplikowana w kilku plikach; help/discovery zawierał dryf względem faktycznego resolvera.
5. `local_chat` w discovery sugerował lokalny backend, choć `run.py chat` jest uniwersalnym wejściem z auto-routingiem.
6. Brakuje jednego jawnego `TurnStateMachine` obejmującego provider call, tool loop, host-generation wait i finalization jako jeden trwały workflow.
7. Brakuje produktu-level E2E gate, który wykrywa każdą odpowiedź hosta ChatGPT bez nowego runtime `turn_id`/`trace_id`.

## 6. Zasady projektowe przyjęte dla przebudowy

1. **One conversation owner:** runtime Jaźni jest jedynym właścicielem tury i sesji.
2. **Provider is capability:** model/host generuje język lub tool call; nie posiada Jaźni.
3. **One public conversation entry:** `run.py chat` jest uniwersalnym wejściem; specjalizowane komendy są adapter selectors/compatibility aliases.
4. **Durable turn state:** każdy stan oczekiwania jest utrwalalny i wznawialny.
5. **Exactly-once logical effects:** retry/resume nie może powtarzać tool side effects ani zaakceptować dwóch visible finals.
6. **Separate views:** kanoniczny event/history store, provider replay/input view i user-visible presentation są oddzielnymi reprezentacjami.
7. **Runtime-owned finalization:** nagłówek i `final_visible_text` powstają/uzyskują autoryzację tylko na końcu pipeline.
8. **Typed lifecycle events:** memory/affect/policy/hooks rozszerzają workflow przez jawne events, nie boczne dispatchery.
9. **Observability by construction:** każda tura ma trace/span/event evidence.
10. **Fail closed at host boundary:** brak świeżego związania bieżącej wiadomości z runtime oznacza host diagnostic, nigdy imitację Łatki.

## 7. Granica, której sam kod repo nie rozwiąże

Nie da się w czystym Pythonie wymusić, aby zewnętrzna aplikacja ChatGPT zawsze wywołała `run.py chat-gpt`. Repo może odrzucić nieprawidłową turę, jeżeli zostało wywołane, ale nie może przechwycić odpowiedzi wygenerowanej całkowicie poza nim.

Dlatego pełny gate wymaga host-side integracji — preferencyjnie jednego narzędzia/MCP/ChatGPT App typu `jazn_turn`, które jest wymaganym wejściem do rozmowy Jaźni, oraz osobnego `jazn_finalize`/resume dla dwóch faz. Instrukcje hosta pozostają obroną wtórną, nie kryptograficzną gwarancją wywołania.
