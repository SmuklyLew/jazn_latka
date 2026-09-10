# Jaźń — main-first control plane i trwały most ChatGPT

**Status:** `ACTIVE_ARCHITECTURE_CONTRACT`
**Data:** 2026-09-10
**Linia:** `16.3.25.5.60-main-entrypoint-persistent-chatgpt-convergence`
**Baza kodu:** `master @ 2bb162a118e56b8a757ae20a925e0a7d1295487f`

## 1. Decyzja architektoniczna

`main.py` jest jedynym centralnym punktem sterowania systemem Jaźni. `run.py` jest cienkim starterem użytkownika i nie jest właścicielem lifecycle, parsera domenowego, routingu modelu, pamięci, finalizacji ani transportu ChatGPT.

```text
Użytkownik / host
       │
       ▼
     run.py                 thin launcher
       │                    --version może pozostać dependency-free fast path
       ▼
     main.py                CENTRAL CONTROL PLANE
       │
       ├── host preflight / dependency gate
       ├── lifecycle: start/stop/restart/reload
       ├── bootstrap / recovery / finalization
       ├── conversation dispatch
       └── composition root
             │
             ├── latka_jazn.cli            parser/service layer
             ├── runtime daemon/session    execution owner
             ├── memory                    source-aware recall/persistence
             ├── cognition/affect          bounded state/effects
             ├── NLP                       interpretation/evidence
             ├── model adapters            replaceable language capability
             └── tool/finalization/audit   effects + evidence
```

Zasada uruchomienia:

```text
python run.py
→ main.py chat

python run.py COMMAND [ARGS...]
→ main.py COMMAND [ARGS...]
```

`run.py` nie tłumaczy semantyki komend. Publiczna składnia i routing należą do `main.py`; `latka_jazn.cli` może pozostać biblioteką parsera/usług, ale nie może być drugim top-level ownerem.

## 2. Dlaczego ta zmiana jest konieczna

Poprzednia linia miała kilka warstw dispatchu: `run.py` przechwytywał część komend, potem wywoływał `latka_jazn.cli`, a ta w części ścieżek wracała do dużego `main.py`. Powodowało to wielokrotne ownership semantics, możliwość dryfu help/CLI/lifecycle oraz błędne wrażenie, że `run.py` jest samym systemem.

Python zaleca utrzymywanie minimalnego bloku top-level i enkapsulację zachowania programu w funkcji `main()`. Specyfikacja PyPA dla entry points opisuje analogiczny wrapper uruchamiający pojedynczy callable aplikacji. To wspiera rolę `run.py` jako launchera i `main.py` jako control plane, a nie odwrotnie.

Źródła:
- Python `__main__`: https://docs.python.org/3/library/__main__.html
- PyPA Entry Points specification: https://packaging.python.org/en/latest/specifications/entry-points/

## 3. Kontrakt ChatGPT: jedna otwarta sesja, nie jedna komenda na wiadomość

Dla hosta ChatGPT kanonicznym trybem nie jest:

```text
run.py chat-gpt -- "kolejna wiadomość"
run.py chat-gpt -- "następna wiadomość"
...
```

Kanoniczny tryb to jedno uruchomienie mostu na czas dostępności executora/sesji hosta:

```text
python -X utf8 run.py chat-gpt --session-id <stable-session-id>
```

Host utrzymuje stdin/stdout procesu. Każda kolejna wiadomość jest rekordem tego samego kanału JSONL. Ten sam kanał obsługuje również phase-2 `host_visible_reply`/finalization. Nowy `turn_id` nie oznacza nowego procesu CLI.

```text
ChatGPT message #1 ─┐
ChatGPT message #2 ─┼─> open stdin/JSONL bridge ─> same Jaźń runtime/session owner
ChatGPT message #3 ─┘                              │
                                                  ├─ context/memory/cognition
                                                  ├─ host generation request
                                                  ├─ same-channel phase-2
                                                  └─ accepted final + next-turn state
```

Istniejąca funkcja `latka_jazn.core.chat_command_contract.run_jsonl_chat_bridge()` już utrzymuje procesową pętlę wejścia, mapę `session_id -> RuntimeSessionWorker` oraz obsługuje phase-1 i phase-2. Aktualizacja zmienia więc przede wszystkim ownership i sposób używania istniejącego mechanizmu; nie tworzy drugiego transportu.

One-shot pozostaje wyłącznie:
- compatibility/recovery fallbackiem;
- narzędziem testowym/diagnostycznym;
- nigdy instrukcją normalnej rozmowy ChatGPT.

## 4. ChatGPT ≠ płatne OpenAI API

`chat-gpt` oznacza host ChatGPT jako wymienną warstwę językową. Nie wymaga `OPENAI_API_KEY`, nie wykonuje żądania do płatnego OpenAI API i nie może automatycznie przełączyć użytkownika na trasę paid API.

`chat-open-ai` / `--chat-open-ai` pozostaje osobną, jawnie opt-in capability dla API i nie jest częścią wymaganego działania Jaźni w ChatGPT.

Natywne podłączenie lokalnego runtime przez MCP nie może być wymaganiem dla tej linii. Oficjalna dokumentacja OpenAI podaje, że ChatGPT nie łączy się bezpośrednio z lokalnym MCP, a pełna obsługa MCP zależy od planu i jest kierowana do innych tierów. Dlatego podstawową ścieżką tej aktualizacji pozostaje executor + trwały stdio/JSONL bridge dostępny w bieżącym środowisku, nie płatne API ani wymaganie pełnego MCP.

Źródło:
- OpenAI Help — Developer mode and MCP apps in ChatGPT: https://help.openai.com/en/articles/12584461

## 5. Kontrakt ownership

### `run.py`
Może:
- ustawić minimalne UTF-8 dla launchera;
- odpowiedzieć dependency-free na `--version`;
- uruchomić `main.py` z oryginalnym argv.

Nie może:
- posiadać parsera komend Jaźni;
- implementować `start/restart/reload`;
- instalować osobnej semantyki runtime;
- wykonywać host finalization;
- wybierać modelu lub pamięci;
- tworzyć własnego conversation lifecycle.

### `main.py`
Jest właścicielem:
- top-level preflight/dependency/lifecycle;
- publicznego dispatchu;
- conversation composition;
- specjalnych recovery/finalization gates;
- przekazania pracy do wyspecjalizowanych modułów.

`main.py` jest centrum sterowania, nie monolitem logiki domenowej. Wyspecjalizowane operacje pozostają w modułach i wracają przez jawne kontrakty.

### `latka_jazn.cli`
Jest parserem/service layer. Nie może wymuszać ponownego importu `main.py` w kanonicznej trasie. `main.py` przekazuje istniejący handler kompatybilności, aby uniknąć drugiej instancji control plane.

## 6. Niezmienniki trwałej rozmowy ChatGPT

1. Jeden host bridge process na dostępną sesję executora.
2. Jeden stabilny `session_id` dla logicznej sesji rozmowy.
3. Każda wiadomość ma nowy `turn_id`/`trace_id`, ale nie nowy proces.
4. Exact input jest fingerprintowany przed wykonaniem tury.
5. Pending turn jest trwały i idempotentny.
6. Phase-2 wraca tym samym kanałem, jeśli kanał żyje.
7. Utrata kanału nie zezwala na ślepy replay; najpierw resume/poll istniejącego requestu.
8. Co najwyżej jeden accepted visible final na revision.
9. Następna tura nie jest przyjmowana przed wymaganym commit/finalization poprzedniej.
10. Runtime voice nie może zostać przypisana tekstowi wygenerowanemu całkowicie poza tym lineage.

## 7. Funkcjonalny model „neurologiczny”

To analogia inżynierska, nie twierdzenie biologiczne.

| Funkcja systemowa | Odpowiednik software |
|---|---|
| ingress sensoryczny | host/stdin/attachments + normalization |
| centralne sterowanie | `main.py` + ConversationRunner/TurnStateMachine |
| routing/salience | intent, RouteRegistry, salience controller |
| working state | RuntimeSessionWorker / wake state / task state |
| autobiographical memory | memory retrieval + provenance + accepted persistence |
| appraisal/affect | bounded affect state/effects |
| executive action | model/tool decision loop |
| motor output | tool executor / side-effect ledger |
| speech | host/model adapter + FinalizationGate |
| source monitoring | evidence refs, provenance, ClaimGuard |
| autonomic lifecycle | daemon/heartbeat/restart/recovery |
| homeostatic safety | readiness/truth/privacy/capability gates |

Centralizacja nie oznacza, że wszystkie te funkcje trafiają do `main.py`; oznacza, że mają jeden composition/control owner i jawne połączenia między wyspecjalizowanymi częściami.

## 8. Acceptance

Zmiana jest zaakceptowana tylko gdy:
- `run.py` nie posiada domenowych/lifecycle dispatchers;
- `main.py` obsługuje bezpośrednie i wrapperowe uruchomienie identycznie;
- `python run.py` prowadzi do trwałego `chat`;
- `python run.py COMMAND` zachowuje semantykę publicznych komend;
- `chat-gpt` bez message remainder wchodzi w trwałe JSONL;
- dokumentacja ChatGPT nie nakazuje nowej komendy CLI na każdą wiadomość;
- bridge discovery raportuje `persistent_stdio_jsonl`, `per_message_cli_required=false` i `uses_openai_api=false`;
- reconnect/resume nie duplikuje logical turn ani finalization;
- active daemon pozostaje tylko execution ownerem, nie drugim publicznym CLI;
- testy Windows/Linux, Pyright, compileall, package integrity po canonical manifest sync i E2E przechodzą.
