# JAŹŃ v127.30.10 — plan aktualizacji, stabilizacji i końcowego odbioru

## 0. Identyfikacja i cel
- Repozytorium: `SmuklyLew/jazn_latka`.
- Bazowa wersja: v127.23.9; gałąź: `fix/v12723-9-session-grounding-continuity`.
- Niezmienny commit bazowy: `9db1993f8734413b370c0325fb1135dfdf42aeba`.
- Docelowa wersja: **v127.30.10**; gałąź: `fix/v12730-10-runtime-architecture-hardening`.
- Cel: jeden niezależny, trwały runtime współpracujący z lokalnymi i zewnętrznymi LLM, bez uzależniania pamięci, tożsamości, ciągłości i lifecycle od modelu, dostawcy lub transportu.
- Tryb: implementacja, testowanie, weryfikacja. Bez merge do master bez osobnej zgody.
- Dokument kontrolny prac, nie prompt osobowości ani zastępcza implementacja. Status wydania na wejściu: NOT_STARTED.

## 1. Architektura i nienaruszalne granice

**Korekta operatora z 2026-11-24 (wiążąca dla v127.30.10): ordinary-chat = remote-only.** ChatGPT nie instaluje Jaźni, nie uruchamia daemona w sandboxie, nie materializuje SYSTEM/MEMORY z uploadów ani Biblioteki. Persistent daemon działa niezależnie na PC/serwerze, uruchamiany i nadzorowany przez operatora. ChatGPT jest klientem MCP i hostem zewnętrznej realizacji językowej, gdy kontrakt jej wymaga. Preferowana publiczna trasa: autoryzowane MCP Streamable HTTP przez stabilny Cloudflare Tunnel do istniejącego gatewaya; alternatywny autoryzowany transport tylko zgodnie z możliwościami hosta (np. Secure MCP Tunnel, z odrębnymi warunkami dostępu). Nie wystawiać prywatnego daemon API ani MEMORY bezpośrednio do internetu. Brak zweryfikowanego MCP oznacza host diagnostic, nie automatyczny lokalny fallback. ZIP/CLI/bootstrap pozostają narzędziami instalacji, dystrybucji i jawnego operator_recovery poza zwykłą rozmową. Nie usuwać działających mechanizmów lokalnego PC/Ollama. Historyczne hybrid_adaptive nie jest domyślną trasą i nie może być wybierane automatycznie; zgodność/migrację istniejących ustawień ustalić jawnie w kodzie i testach. Utrata połączenia z ChatGPT nie zatrzymuje daemona. Transport nie jest właścicielem finalizacji ani trwałej sesji.

```text
CLI / ChatGPT-MCP / Studio / inni klienci
                 |
           kanoniczny daemon
  lifecycle | routing | kontekst | pamięć
  truth gate | provenance | finalizacja | persistence
          /                          \
 lokalny adapter LLM          zewnętrzny adapter/bridge LLM
```

Rozróżniać niezależnie lokalizację daemona, lokalizację inferencji, dostawcę, transport (CLI/HTTP/MCP), realizację odpowiedzi (deterministyczna/lokalna/zewnętrzna), właściciela finalizacji i gotowość MEMORY. Ollama może także obsługiwać inferencję chmurową; MCP nie jest modelem. Jeden wspólny rdzeń, nie trzy systemy. `run.py` pozostaje cienkim starterem, `main.py` centralnym control plane, `latka_jazn/cli.py` właścicielem parsera i usług. Studio jest klientem. LLM realizuje zadanie językowe, nie zatwierdza własnej odpowiedzi, nie przejmuje pamięci ani lifecycle. Awaria LLM nie implikuje zatrzymania daemona; jawnie raportować ograniczoną zdolność. Zmiana modelu nie zmienia sama w sobie tożsamości. Host nie imituje nieaktywnej Jaźni. Brak obowiązkowego płatnego API dla lokalnego i istniejącego chat-gpt.

## 2. Dowody bazowe i rejestr usterek
Bazowy release-hardening Ubuntu: 4464 PASS, 1 FAIL, 25 SKIP, dodatkowo 6 zaliczonych subtestów. Lokalnie 12 + 53 zaliczenia pytest (liczba zaliczeń przebiegów, nie gwarantowana liczba unikalnych testów). Persistent Runtime E2E na Ubuntu i Windows zaliczony w poprzednim odbiorze. Rzeczywisty izolowany daemon Windows, Ollama gemma3:latest, port 8796, MEMORY off: 8 zapisanych tur (7 główna sesja, 1 odrębna), 0 błędnych rekordów; integralność SYSTEM i source provenance, start i gotowość, odczyt Mira, konflikt z Jodła, korekta Sokół, izolacja, ponowne połączenie klienta i graceful shutdown potwierdzone. Dowody dotyczą bazowego SHA, nie nowego wydania; ponowne połączenie klienta nie oznacza restartu procesu. Rzeczywista aktywacja Jaźni w ChatGPT niepotwierdzona. Archiwa projektu nie stanowią dowodu aktywacji.

| ID | Problem | Stan początkowy |
|---|---|---|
| J-001 | RecoveryPolicy.resolve 166 linii przy limicie 150 | FAIL |
| J-002 | Lokalna tura finalized_successfully=false mimo not_required i poprawnych dowodów | Niespójność |
| J-003 | session_loaded_from=new mimo ciągłości | Do ustalenia semantyki |
| J-004 | session_reused=false przy tym samym ID | Do analizy |
| J-005 | Nazwa obiektu błędnie utożsamiona z imieniem użytkownika | Obserwacja |
| J-006 | Bazowy interpreter widoczny mimo startu z venv | Do diagnostyki |
| J-007 | Ciągłość po restarcie daemona | NOT_RUN |
| J-008 | Rzeczywisty runtime/transport ChatGPT | NOT_RUN/BLOCKED, ustalić capability |
| J-009 | Autobiograficzna MEMORY | NOT_RUN |
| J-010 | Automatyczny pełny test publicznego ingress | Luka |
| J-011 | wal_reset_mitigation_required=true | Do diagnostyki |
| J-012 | Ordinary-chat nadal dopuszcza automatyczny ZIP/bootstrap (hybrid_adaptive) | Potwierdzona rozbieżność z korektą architektury |

## 3. Etapy implementacji i bramki

### 00 — Stan początkowy i gałąź
Zweryfikować branch, HEAD lokalny/zdalny, clean worktree (lub jawnie ograniczenie API), AGENTS.md, AGENTS.codex.md i właściwe zagnieżdżone instrukcje. Zabezpieczyć stan i dowody; utworzyć dokument postępu i rejestr usterek. Bramką jest jednoznaczny punkt bazowy, odrębna gałąź, możliwość wycofania. Nie nadpisywać cudzej pracy.

### 01 — Audyt architektury i zależności
Zlokalizować i wczytać w całości wybrane źródła, bezpośrednie zależności, kontrakty i testy. Ustalić właścicieli lifecycle, engine, routing, adapterów/executor preflight, kolejki, finalizacji, MEMORY, continuity, konfiguracji, transportów, bootstrap i Studio. Zidentyfikować nieuzasadnione zależności rdzenia od LLM/transportu; zapisać mapę modułów i publicznych kontraktów. Nie przepisywać architektury na zapas. Zbadać istniejący remote_only, hybrid_adaptive, operator_recovery, wszystkie domyślne wartości, generatory loaderów, kontrakty JSON, GUI/CLI i testy; wykorzystywać istniejący gate, nie tworzyć drugiego.

### 02 — Refaktoryzacja RecoveryPolicy (J-001)
Wydzielić projekcję VerifiedSessionQuote z resolve do funkcji pomocniczej bez zmiany kolejności walidacji, mutacji stanu i projekcji handlera. Nie zmieniać limitu hotspotu. Testy: test_known_hotspot_functions_do_not_grow, poprawny fakt, odrzucenie złego kandydata, brak dowodów, konflikt, handler deterministyczny i zwykła odpowiedź modelowa. Bramką jest limit <=150 i zachowanie kontraktów. Checkpoint, commit, push po potwierdzeniu.

### 03 — Finalizacja (J-002)
Zbadać main.py::_daemon_cli_completion oraz kanoniczne usługi i docs/runtime/TURN_FINALIZATION_CONTRACTS.md. Obecna lokalna tura: host_finalization_gate_state=not_required, canonical_persistence_ok=true, execution_state=final_visible_answer, finalized_successfully=false. Nie zmieniać flagi bez dowodu. Rozdzielić ukończenie joba, gotowość odpowiedzi, oczekiwanie na hosta, zaakceptowaną finalizację i persistence. Deterministyczny handler, lokalny LLM i zewnętrzny LLM dostarczają kandydatów do wspólnej walidacji/finalizacji runtime. Testy pozytywne lokalnej, deterministycznej i hostowej ścieżki; negatywne: pending, niepoprawny hash, envelope, wymagany zapis, inna tura/instancja, powtórzona finalizacja, timeout/wznowienie tego samego requestu. Zachować rygor hosta, fail-closed i brak replayu.

### 04 — Pamięć sesyjna i continuity (J-003/004/007)
Analiza conversation_state_store, session_fact, session_history_claim_guard, conversation_runner, local_model_context_compiler i modułów checkpoint/recovery. Ustalić semantykę session_loaded_from, session_reused, session_resurrected_from_disk, continuity_generation, continuity_checkpoint_sha256, engine_reused_between_turns, process_reused. Proces != sesja != odzyskanie z dysku. Nie kosmetycznie zmieniać flag. Testy: kolejna tura, reconnect, restart izolowanego daemona, zmiana LLM, przerwana tura, uszkodzony checkpoint, konflikt, korekta, równoległe sesje i idempotencja request ID. Bramką jest dowód ciągłości w stanie runtime, nie kontekście modelu.

### 05 — Niezależność LLM i daemona
Audyt adapterów, model executor, routing, degradacja, timeout/retry/circuit breakers. Macierz: daemon gotowy + tylko lokalny LLM => lokalnie; tylko zewnętrzny => jeśli autoryzowane; oba => routing zgodny z kontraktem; żaden => żywy rdzeń z ograniczoną funkcją; daemon niedostępny => brak potwierdzonej Jaźni niezależnie od LLM. Nie przełączać niejawnie prywatnych danych do zewnętrznej inferencji, nie zmieniać trasy już przyjętej tury. Weryfikować faktyczną lokalizację inferencji. Brak ChatGPT/MCP nie blokuje lokalnego Ollama ani rdzenia. Brak Ollama nie blokuje autoryzowanej zewnętrznej realizacji, gdy kontrakt na to pozwala. Dostępny executor ChatGPT nie jest przesłanką do lokalnego startu.

### 06 — Semantyka (J-005)
Ustalić, czy błąd dotyczy modelu, ekstrakcji, kontekstu, walidacji lub zapisu. Rozróżnić autora, podmiot i typ informacji. Przykłady: Mam na imię Adam => imię rozmówcy; Projekt nazywa się Adam => nazwa projektu; Nazwa to Mira => podmiot nieokreślony; Łatka powiedziała… => właściwe autorstwo; Poprawka: nazwa to Sokół => właściwy rekord korekty; niejednoznaczność => niepewność. Testować różne dane i sformułowania w zakresie kontraktu; bez wyjątków na słowa testowe.

### 07 — Lifecycle, Python i venv (J-006)
Zweryfikować interpreter procesu potomnego, sys.prefix/base_prefix, importy i zależności; ścieżka procesu Windows sama nie rozstrzyga venv. Zachować tryby A user-managed (bez auto-instalacji), B hybrid (kontrolowane brakujące dodatki), C full auto (polityka projektu). Start/warm/restart/reload/stop/recovery/supervisor/utrata transportu. Bez konkurencyjnych instancji i nieautoryzowanych instalacji.

### 08 — MEMORY i zapis (J-009/011)
Rozróżnić sesję, autobiografię, stan operacyjny i kontekst LLM. Testy integralności, źródeł, odczytu epizodycznego, zapisu, transakcji, recovery, izolacji; SQLite/WAL i osobno transactional tier oraz legacy runtime_write. Zbadać wal_reset_mitigation_required; nie zakładać awarii. Dla dotkniętego SQLite: integrity_check, foreign_key_check, zgodność shardów. Wyłącznie syntetyczne dane/zweryfikowana kopia, bez modyfikacji prywatnej MEMORY.

### 09 — Transport zewnętrzny, ChatGPT/MCP/Cloudflare (J-008/012)
Zweryfikować jazn_status, jazn_generate_visible_reply, jazn_resume_visible_reply, jazn_finalize_reply oraz autoryzację, instancję, kontrakt, lineage, readiness i heartbeat. Testy handshake, odmowa nieuprawnionego dostępu, niezgodny kontrakt, timeout i reconnect bez replayu, odrzucenie złej odpowiedzi hosta, accepted finalization i brak imitacji przy niedostępności. Sesja != transport. Testy symulowane CI nie są żywym odbiorem ChatGPT. Brak capability => BLOCKED/NOT_RUN, nie PASS. Bez obowiązkowego klucza OpenAI API dla realizacji przez ChatGPT host bridge; wymagane poświadczenia transportu są odrębną kwestią. Odbiór rzeczywisty: autoryzowany stabilny HTTPS MCP przez Cloudflare Named Tunnel, publiczny gateway bez ujawniania prywatnego daemona, negatywne auth/scope/audience/origin, timeout i reconnect, czat bez ZIP i bez lokalnego executora. Sam tunel lub URL nie dowodzi gotowości. Nie instalować/konfigurować tunelu ani zmieniać auth bez odrębnej zgody operatora. Jeśli brak bieżącej ekspozycji czterech narzędzi MCP, fail-closed i wskazanie problemu; bez automatycznego recovery.

### 10 — Migracja loadera do remote-only; dystrybucja i operator recovery (J-012)
Ordinary-chat: sprawdzenie rzeczywiście callable czterech narzędzi -> świeży jazn_status -> verified remote -> jedna tura -> accepted finalization; przy braku gotowej trasy host_diagnostic. Bez prób executora, discovery ZIP, Biblioteki, materializacji, rozpakowania, startu daemona lub handoffu. Audyt i zbieżność AGENTS.chatgpt.md, generatora instrukcji projektu, zasobów JSON, policy/preflight/capability i wszystkich wywołań; nie poprzestawać na redakcji dokumentacji. Testy zwykłej rozmowy z dostępnym executorem i brakiem MCP muszą dowodzić braku bootstrapu; podobnie dla błędnego/starego statusu. Jawny operator_recovery (Work/Codex/PC) zachowuje bezpieczną instalację, warm/resume/cold, SHA/CRC, pełną ekstrakcję, manifest, provenance, preflight/start/live status, oddzielną MEMORY i negatywne testy archiwów. ZIP jest opcjonalnym formatem dystrybucji, nie warunkiem runtime ani integracji ChatGPT. Nie usuwać bezpiecznych narzędzi operatora ani nie modyfikować istniejącej prywatnej MEMORY.

### 11 — Automatyzacja odbioru i JSS (J-010)
Automatyczny test przez publiczny ingress: izolowany start i tożsamość, zapis i odczyt faktu, reconnect, konflikt, odmowa rozstrzygnięcia, jawna korekta, odczyt z SHA/turn/trace źródła, druga sesja, zmiana modelu jeśli dostępny, kanoniczny restart, odczyt po restarcie, finalizacja wszystkich tur, graceful shutdown. Każdy scenariusz zostawia dowód. Dodać osobne scenariusze gateway/Cloudflare/MCP, restartu klienta i niedostępności MCP bez automatycznego bootstrapu; symulowane CI odróżnić od live ChatGPT. Studio używa usług SYSTEM, nie tworzy alternatywnego runtime. Zsynchronizować katalog scenariuszy i istniejące TXT/JSON/JUnit, niezmienną macierz JSS i test evidence/RunStore według AGENTS.

### 12 — Wersja i wydanie
Wersję aktualizować w tej samej zmianie wydaniowej co patch SYSTEM. Ustalić kanoniczny pełny numer v127.30.10, startup_contract, deployment.contract, pozostałe miejsca wersji, katalog JSS, docs, zgodność dystrybucji (SYSTEM ZIP tylko jeśli wytwarzany jako artefakt) i kompatybilność MEMORY. Manifest i provenance wyłącznie kanonicznym generatorem na clean worktree:
```sh
python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json
```
Sprawdzić idempotencję po commicie metadanych. Jeżeli CI generuje commity, zweryfikować ich zakres i końcowy SHA. Nie wpisywać ręcznie hashy. Release build z czystego commita.

### 13 — Regresja i CI
Testy celowane, historyczne, strukturalne, negatywne, funkcjonalne, bezpieczeństwa, compileall, pyright, doctor, package-smoke i pełna deterministyczna regresja. Macierz według aktualnych workflow: persistent-runtime-e2e, release-hardening, pyright-active-tree-audit, MCP conformance, container/Compose, memory-cloud, host-spawn-memory-convergence, Stable test contracts, Node 24, monitor, JSS/Studio. Sprawdzić triggery i required checks; workflow pominięty nie jest zaliczony. Raportować wszystkie skip i przyczyny. Nie osłabiać testów. Testy aktualnego SHA, nie wcześniejszego. Dla zmienianych istniejących testów snapshot append-only wg AGENTS.codex.md.

### 14 — Odbiór i publikacja
Niezależny odbiór A: daemon/rdzeń; B: lokalny LLM; C: rzeczywisty zewnętrzny LLM/ChatGPT przez autoryzowane MCP/Cloudflare bez ZIP/executora; D: autobiograficzna MEMORY; E: niezależna dystrybucja i jawny operator recovery (ZIP opcjonalny); F: narzędzia operatorskie. Brak capability oznacza BLOCKED lub NOT_RUN dla danego odbioru; nie unieważnia dowodów innych obszarów, ale blokuje deklarację pełnego odbioru. Procedura rollback, raport i PR dopiero po wymaganych kontrolach, bez merge bez zgody.

## 4. Procedura realizacji i checkpoint
Cykl każdego etapu: analiza -> test odtwarzający -> minimalna implementacja -> testy/diff -> checkpoint, commit i push -> kontrola zdalnego SHA i CI. Wykonywać prace równolegle z CI tylko gdy bezpieczne; nie nadpisywać auto-commitów. Rejestr: IMPLEMENTATION_PLAN.md, IMPLEMENTATION_PROGRESS.md, ARCHITECTURE_AUDIT.md, DEFECT_REGISTER.md, ACCEPTANCE_MATRIX.md, FINAL_REPORT.md (tworzyć wraz z rzeczywistymi dowodami).
Statusy: NOT_STARTED, ANALYZING, IMPLEMENTING, TESTING, FAILED, BLOCKED, PASS, VERIFIED, NOT_RUN, SKIP. Nie oznaczać PASS bez dowodu. Każdy problem ma ID, przyczynę, moduły, test, rozwiązanie, wynik i SHA.
Checkpoint: release, branch, base_commit, current_head, remote_head, current_stage, stage_status, completed_tasks, modified_files, executed_tests, failed_tests, pending_tests, known_blockers, architectural_decisions, working_tree_clean, push_verified, next_safe_action. Tylko rzeczywiste wartości.

## 5. Limity i bezpieczeństwo
Maks. 70% puli 5h; 60% checkpoint, 65% bez dużych nowych etapów, 70% zakończenie atomowej operacji. Oddzielna pula tygodniowa. Brak licznika => usage_unknown. Nie kupować kredytów. Bez force push, merge, osłabiania testów, równoległych lifecycle, publikowania prywatnych baz/sekretów, zmiany produkcji, niejawnego zewnętrznego transferu, nieautoryzowanych zależności/płatnego API. Nie rozszerzać zakresu bez przyczyny. Publikować tylko dane testowe i dozwolone dowody.

## 6. Definition of Done
- [ ] Potwierdzone usterki rozwiązane lub jawnie rozliczone, bez wykrytej regresji.
- [ ] Jeden rdzeń i rozdzielone adaptery; finalizacja zgodna z kontraktami.
- [ ] Sesja zachowana po restarcie i zmianie modelu, źródła i izolacja potwierdzone.
- [ ] MEMORY zweryfikowana na bezpiecznych danych.
- [ ] Rzeczywiste niezależne odbiory lokalnego i zewnętrznego LLM.
- [ ] Integralność, provenance i zgodność wersji niezależnie od sposobu instalacji; opcjonalny SYSTEM ZIP i bootstrap zweryfikowane jako narzędzia dystrybucji/operatora.
- [ ] Ordinary-chat wyłącznie przez zweryfikowane zdalne MCP; test braku ZIP, lokalnego executora, automatycznego startu i handoffu oraz prawidłowego fail-closed przy niedostępnym MCP. Rzeczywisty odbiór Cloudflare/MCP oddzielnie od testów protokołu.
- [ ] Wszystkie wymagane kontrole CI aktualnego SHA; skip wyjaśnione.
- [ ] Dokumentacja, kontrakty, kod i dowody zgodne i zapisane.
- [ ] Procedura wycofania i raport końcowy.
Brak dowodu nie jest zaliczeniem. Pełny odbiór wszystkich środowisk wymaga wszystkich właściwych bramek.

## 7. Źródła
- [Bazowy kod](https://github.com/SmuklyLew/jazn_latka/tree/9db1993f8734413b370c0325fb1135dfdf42aeba)
- [Release Hardening](https://github.com/SmuklyLew/jazn_latka/actions/runs/45487563276)
- [Persistent Runtime E2E](https://github.com/SmuklyLew/jazn_latka/actions/runs/45487563038)
- [NIST IR 8397](https://csrc.nist.gov/pubs/ir/8397/final), [SSDF](https://csrc.nist.gov/pubs/sp/800/218/final)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
- [OpenAI — Connecting custom MCP servers](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [Cloudflare Tunnel — fundamentals](https://developers.cloudflare.com/tunnel/concepts/), [routing](https://developers.cloudflare.com/tunnel/concepts/routing/)
- [Ollama API](https://docs.ollama.com/api/introduction), [Cloud](https://docs.ollama.com/cloud)
- [GitHub status checks](https://docs.github.com/en/pull-requests/reference/status-checks), [workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs)
- [pytest integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- Przekazane przez operatora logi PowerShell/VS Code i obserwacje izolowanego runtime.

## 8. Stan wejściowy
Plan jest Markdownową wersją ustalonego planu rozmowy, bez elementów interaktywnych. Stan historyczny planu przed rozpoczęciem: 0/15. Bieżący postęp w IMPLEMENTATION_PROGRESS.md. Korekta remote-only z 2026-11-24 ma pierwszeństwo nad wcześniejszą interpretacją bootstrapu. Brak potwierdzonego runtime ChatGPT. Plan nie jest dowodem wykonania. Nie zmieniać kodu poza określonym zakresem bez udokumentowanego uzasadnienia.
