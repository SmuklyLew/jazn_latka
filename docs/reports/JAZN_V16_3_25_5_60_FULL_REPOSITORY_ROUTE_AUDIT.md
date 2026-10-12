# Jaźń v16.3.25.5.60 — full-repository route audit

**Status:** `IMPLEMENTATION_AUDIT / PRE-CI`
**Data:** 2026-09-10
**Audytowany master:** `2bb162a118e56b8a757ae20a925e0a7d1295487f`
**Pakiet źródłowy kodowo równoważny:** `16.3.25.5.59-conversation-runtime-orchestration-convergence`
**Branch roboczy:** `upgrade/v16.3.25.5.60-main-entrypoint-chatgpt-live-convergence`

## 1. Metoda i zakres

Audyt nie bazuje na losowych grepach. Odczytano pełne bajty każdego wpisu systemowego ZIP powiązanego z v59, a wszystkie pliki Python przeanalizowano przez AST. GitHub potwierdził, że bieżący `master` po merge v59 dostał później wyłącznie synchronizację `SOURCE_PROVENANCE.json` oraz `PACKAGE_INTEGRITY_MANIFEST.json`; executable/source tree pozostaje kodowo zgodne z audytowanym pakietem.

Snapshot wejściowy:

```text
archive files:        1304
uncompressed bytes:   11,155,147
Python files:         1020
classes:              1080
functions/methods:    8382
imports:              8116
call expressions:     77,901
AST parse errors:     0
```

Dodatkowo wykonano pełny call/import inventory na kopii roboczej po centralizacji. Największe warstwy źródłowe to `latka_jazn/core`, pamięć, runtime/daemon, CLI/bridge i narzędzia pakowania. Audyt traktuje wszystkie pliki jako elementy grafu zależności, a nie tylko entrypointy.

## 2. Główne ustalenie: top-level ownership był rozszczepiony

Przed v60 ścieżka wejścia wyglądała w praktyce jak:

```text
run.py
  ├── dependency/bootstrap/lifecycle fast paths
  ├── restart/reload
  ├── runtime-bootstrap
  ├── host-finalize
  ├── overlays
  └── latka_jazn.cli
        └── legacy bridge
              └── main.py
```

To oznaczało kilku właścicieli top-level flow i powodowało dryf semantyki komend oraz błędny kontrakt ChatGPT per-message CLI.

Po v60:

```text
run.py
  └── main.py
        ├── preflight/bootstrap/lifecycle
        ├── public command dispatch
        ├── finalization/recovery gates
        └── latka_jazn.cli (parser/service layer)
              └── wyspecjalizowane moduły
```

`main.py` jest centralnym composition/control ownerem; nie oznacza to monolitu domenowego.

## 3. ChatGPT: problem był transportowy, nie tylko instrukcyjny

Stara instrukcja uruchamiała dla każdej wiadomości osobne:

```text
python run.py chat-gpt -- "message"
```

To utrzymywało daemon, ale nie utrzymywało jednego host-side kanału rozmowy. Tymczasem kod już posiada `run_jsonl_chat_bridge()`, który może utrzymywać mapę `session_id -> RuntimeSessionWorker`, czytać wiele rekordów z jednego stdin i obsługiwać phase-1/phase-2 w jednej pętli procesu.

v60 ustanawia kanoniczny kontrakt:

```text
one host bridge process
  + stable session_id
  + many JSONL turns
  + same-channel phase2/finalization
  + persistent daemon execution owner
```

One-shot zostaje tylko jako compatibility/diagnostic/recovery fallback.

## 4. Macierz warstw i ryzyk

| Warstwa | Stan | Ryzyko | Kierunek |
|---|---|---|---|
| launcher | `run.py` był zbyt gruby | drugi control plane | thin launcher → `main.py` |
| central dispatch | rozproszony | dryf komend/lifecycle | jeden owner w `main.py` |
| CLI | parser + legacy dispatch | konkurencyjny owner | parser/service layer |
| daemon | persistent | PID mylony z aktywną turą | per-turn lineage evidence |
| ChatGPT bridge | JSONL już istnieje | per-message process | persistent stdio/JSONL |
| finalization | istnieje | host bypass / duplicate | same lineage + idempotency |
| memory | wiele warstw/fasad | source ambiguity | jedna jawna retrieval facade |
| cognition | wiele wyspecjalizowanych modułów | boczne efekty trudne do zmierzenia | lifecycle events + effect ledger |
| affect | moduły istnieją | antropomorficzny naming / causal ambiguity | bounded measurable projections |
| NLP | osobne lexical/reasoning layers | niejednolity provenance | evidence-aware normalization contract |
| model routing | ChatGPT/Ollama/API rozdzielone | paid API może wyglądać jak równoważny default | ChatGPT host no-key first; paid API explicit opt-in |
| tools | runtime ownership foundations | retry side effects | idempotency ledger + durable tool states |
| source truth | guards/provenance istnieją | vividness/affect może przebić evidence | ClaimGuard/source monitoring gate |
| MCP | private stdio server istnieje | product-plan dependency | optional transport only |
| attachments | osobny otwarty zakres | untrusted ingress | provenance + staging + capability gate |
| release/package | manifest/provenance hardening istnieje | ręczne edycje manifestu | canonical release-hardening sync |

## 5. Główne węzły sprzężenia

AST potwierdza, że `main.py` jest już dużym hubem: importuje dziesiątki komponentów `core` i kilka warstw pamięci. Po v60 ma być właścicielem kompozycji, ale nie powinien dalej pochłaniać implementacji domenowej.

Najbardziej złożone moduły według liczby wywołań w snapshotach to m.in.:
- `latka_jazn/core/runtime_daemon.py`;
- `latka_jazn/core/engine.py`;
- `main.py`;
- `latka_jazn/core/chat_command_contract.py`;
- pamięć/normalizacja i narzędzia rebuild/restore.

To wskazuje naturalne miejsca kolejnych rozcięć kontraktowych: `ConversationRunner`, `TurnStateMachine`, `ContextBuilder`, `FinalizationCoordinator`, a nie kolejne top-level launchery.

## 6. „Neurologiczna” mapa połączeń

Terminologia jest funkcjonalna. Nie oznacza biologicznego mózgu ani świadomości.

```text
INGRESS
  ↓
Input normalization + provenance
  ↓
SESSION / WAKE STATE ───────────────┐
  ↓                                 │
Turn admission / task state         │
  ↓                                 │
ContextBuilder                      │
  ├── source-aware memory ◄─────────┤
  ├── current goals/task            │
  ├── bounded affect/salience       │
  └── capability/tool policy        │
  ↓                                 │
Decision / ModelRouter              │
  ├── ChatGPT host                  │
  ├── Ollama                        │
  └── paid API only if explicit     │
  ↓                                 │
ToolLoop / external effects         │
  ↓                                 │
Claim/source gate                   │
  ↓                                 │
FinalizationGate                    │
  ↓                                 │
Accepted event + memory/state commit┘
  ↓
VISIBLE OUTPUT
```

Celem nie jest „więcej modułów”, tylko lepsza causal connectivity: każdy moduł ma jawne wejście, wyjście, allowed effect, provenance i test ablation.

## 7. Priorytety naprawy

### P0 — zakończyć v60
- main-first control plane;
- thin `run.py`;
- trwały ChatGPT stdin/JSONL;
- same-channel phase2;
- brak per-message CLI w aktywnych instrukcjach;
- no-paid-API invariant;
- command parity tests;
- package manifest sync przez release workflow.

### P1 — jeden `ConversationRunner`
Przenieść orkiestrację z dużego `main.py` do testowalnego service object, ale `main.py` pozostaje composition ownerem. `latka_jazn.cli` nie może mieć konkurencyjnego lifecycle.

### P2 — trwała `TurnStateMachine`
Każde oczekiwanie (model/tool/host/finalize) jest stanem z `event_seq`, idempotency i crash recovery.

### P3 — typed event connectivity
Memory/affect/NLP/policy/telemetry podpinają się do jawnych lifecycle events. Wprowadzić bounded queue/event bus tylko wtedy, gdy pomiar pokaże potrzebę asynchronii; nie robić „async everywhere”.

### P4 — memory/source monitoring
Jedna fasada recall z `EvidenceRef`, temporal/source discrimination, abstention i knowledge update tests.

### P5 — cognition/affect causal verification
Każdy affect/salience effect ma limit, reason i ablation. Affect nie może być źródłem faktu autobiograficznego.

### P6 — host E2E
10+ kolejnych tur w jednej aktywnej sesji: każda ma fresh turn lineage, phase2, accepted final, next-turn acceptance; celowo zerwany kanał ma się wznowić bez duplicate turn.

## 8. Baza badań

- Python `__main__`: minimalny top-level + `main()` — https://docs.python.org/3/library/__main__.html
- PyPA Entry Points — https://packaging.python.org/en/latest/specifications/entry-points/
- OpenAI Help, MCP/Developer Mode — https://help.openai.com/en/articles/12584461
- Sumers et al., *Cognitive Architectures for Language Agents* — https://arxiv.org/abs/2309.02427
- Wu et al., *LongMemEval* — https://arxiv.org/abs/2410.10813
- Johnson, Hashtroudi, Lindsay, *Source monitoring* — https://pubmed.ncbi.nlm.nih.gov/8346328/

Wnioski naukowe są używane jako inspiracja do modularności, pamięci, decision/action i source attribution; nie certyfikują fenomenalnych własności systemu.

## 9. Evidence wymagane przed merge

- compileall całego aktywnego drzewa;
- Pyright bez osłabienia konfiguracji;
- targeted launcher/main/ChatGPT/daemon/finalization tests;
- pełny deterministic pytest profile;
- Windows path/ConPTY tests;
- persistent JSONL multi-turn E2E;
- reconnect/recovery + no duplicate final;
- `doctor` i `package-smoke` dopiero po canonical manifest/provenance sync;
- CI branch green.

Ten raport nie oznacza `MERGED`, `LIVE` ani `ACCEPTED`; jest evidence audytu i planu implementacji.
