# v127.30.10 — rzeczywisty odbiór Windows: ustalenia i plan naprawczy

- Data odbioru: 2026-11-26.
- Testowany SHA: `282dc4e821ef5bf5815b4f4f7860f98c385931db`.
- Gałąź źródłowa: `fix/v12730-10-runtime-architecture-hardening`.
- Gałąź naprawcza: `fix/v12730-10-pc-acceptance-remediation-20261126`.
- Decyzja: **RELEASE BLOCKED / etap 05 niezakończony.** Etap 06 nie może być oznaczony jako rozpoczęty po pozytywnym odbiorze.
- Źródło: wyniki PowerShell/Python/Ollama przekazane przez operatora w rozmowie; nie są to samodzielnie uruchomione testy agenta ani pełny eksport logów. Zachować oryginały lokalnie; nie commitować workspace_runtime, MEMORY, sekretów ani pełnych logów zawierających ścieżki lub dane prywatne.

## 1. Stan odbioru

| Obszar | Status | Dowód / ograniczenie |
|---|---|---|
| OR-01 środowisko | PASS po naprawie venv | Python 3.14.4 win-amd64; pierwotne wheele cp313 dla charset-normalizer 3.4.4, jiter 0.12.0, numpy 2.3.4 zastąpiono zweryfikowanymi cp314 tych samych wersji; importy i pip check PASS. Duplikat metadanych pip 25.3 usunięty z aktywnego site-packages przez operatora po weryfikacji 469 plików pip 26.1.2; nie dowodzi usterki SYSTEM. |
| OR-02 | PASS | 30 plików test_stage05, 280 passed in 35.91s, exit 0. |
| OR-03 | PARTIAL | Gemma3:latest Q4_K_M lokalnie przez /api/chat, bez cloud i płatnego API. Zaakceptowany stan rozmowy i MessageEnvelope; niespójna/niejasna projekcja CLI finalizacji, jakość odpowiedzi wymaga rozliczenia. |
| OR-04 | PARTIAL | Realne przerwanie /api/chat po 206 tokenach, HTTP 500, ten sam daemon ready, 0 pending, odczyt tego samego requestu nie tworzył nowych zadań. Nieudana klasyfikacja/odzyskanie odrzuconego zadania; pełny circuit breaker OPEN/HALF_OPEN niepotwierdzony. |
| OR-05 | FAIL | Osiem z dziewięciu roboczych kontroli technicznych PASS, blokada trwałej idempotencji. |
| OR-06 | NOT_RUN | Nie uznawać gotowości do wdrożenia. |

## 2. Zachowane pozytywne dowody

- Odtworzenie sesji przed restartem: 18/18 niezależnych kontroli artefaktów; izolacja nowej sesji: 20/20 technicznych kontroli, ale nie jest to dowód semantycznej prawdziwości odpowiedzi.
- Restart kanoniczny `reloaded`, stop/start OK; poprzednia i nowa instancja różne, root i wersja te same, live endpoint, marker, package integrity, source provenance oraz heartbeat potwierdzone.
- Stan dialogowy sesji Mira przed/po restarcie ma identyczny SHA-256 `5e95754c82da028763b1daef0668ad89b30dbda4ee02388b6f2b0f50f1dfb185`. Dwa rekordy rozmowy identyczne bajtowo; checkpoint generacja 4 → 6, nadal dwie tury; 11/11 niezależnych kontroli. Zmiana hasha całego checkpointu nie jest utratą stanu. Nie ustalono dokładnego powodu dwóch zapisów metadanych.
- Pierwsza tura po restarcie: 34/34 kontroli, odzyskano historię dwóch tur z dysku, właściwy wejściowy checkpoint, odpowiedź Mira, generacja 7 i trzy utrwalone tury. MEMORY optional off, bez dowodu autobiograficznej ciągłości.
- Historyczny poll: 11/11 kontroli braku skutków ubocznych, brak nowych zgłoszeń/ukończeń/odrzuceń, niezmienione pliki sesji i rekordy. Nie jest to dowód odporności admission na wszystkie duplikaty.
- Pierwotna niezgodność hasha tekstu wynikała z dekodowania konsoli PowerShell IBM852; niezależne pobranie bytes przez Python UTF-8 dało zgodny surowy hash. Nie naprawiać tej obserwacji przez normalizowanie tekstu zaakceptowanego przez runtime.

## 3. Defekty i obserwacje do rozliczenia

### F01 — P0 — trwała idempotencja przyjętych żądań — CONFIRMED

Rejestr `workspace_runtime/daemon_chat_jobs.json` zawierał 6 z 9 przyjętych żądań z fingerprintami. Wszystkie 6 poprawnie zakończonych zachowano, wszystkie 3 odrzucone pominięto.

| Przypadek | Request ID | Wpis |
|---|---|---|
| Pierwsza tura Mira | fc6599a6-219c-4933-8ba0-757a3027b016 | jest |
| Offline 1 | f4aba5ce-5234-490d-a350-4467ca13b171 | brak |
| Offline 2 | 49c41ae2-73dd-4266-9e7e-4fbbdb3f8f1e | brak |
| Esej 1 | d933a088-b0c9-4096-b0dc-87a8f6aeb1f0 | jest |
| Esej 2 | 1d803371-e266-46da-bca3-0e1ab1b64375 | jest |
| Awaria podczas inferencji | be2c7994-51ae-42c5-ac55-dd58dae64ebd | brak |
| Odzyskana sesja | 1c4cf185-376e-41a2-a142-4f8bfe66f0f1 | jest |
| Izolacja sesji | 14838520-4707-42b6-afa1-705be222fb17 | jest |
| Po restarcie | 2fe03ebb-32e7-4e56-8871-2f620fda6752 | jest |

Przed restartem trzy przyjęte tury kończyły się jako `host_finalization_rejected`; w przypadku rzeczywistej awarii `host_finalization_contract_not_persisted`. Po restarcie poll przerwanej tury: `chat_job_not_found`, exit 1. Historyczne poprawnie ukończone tury: `recovered_after_restart` / `completed_request_result_unavailable`; pełna odpowiedź niedostępna. Najnowsza tura: completed, integralność PASS.

W testowanym SHA funkcja `_persist_chat_jobs_locked_unsafe()` pomija terminalne zadania inne niż completed tombstone lub szczególny failed/runtime_turn_not_accepted. `submit_chat_job()` konsultuje bieżące zadania i trwałe tombstones. Brak trwałego wpisu oznacza ryzyko ponownego admission; rzeczywisty replay celowo NOT_RUN na instalacji dowodowej. Nie utożsamiać braku wpisu z dowodem faktycznego ponownego wykonania ani nie zakładać, że brak innego mechanizmu zabezpieczającego został już udowodniony dla wszystkich kanałów.

Kryteria naprawy:
- trwałe, atomowe związanie request ID i fingerprintu przed pierwszym wykonaniem/ACK, pełna lineage i właściciel/autoryzacja w zakresie istniejącego kontraktu;
- zachowanie wszystkich przyjętych stanów terminalnych (w tym failed, timeout, cancelled, host_finalization_rejected, expired i stanów odzyskanych), przyczyny i bezpiecznego publicznego statusu, oddzielnie od payloadu;
- brak nowej inferencji, zapisu rozmowy lub finalizacji przy tym samym request ID po restart/TTL; odmowa konfliktu fingerprintu lub principal bez ujawniania danych; nie tworzyć wpisów przy odmowie przed admission;
- retencja identyfikatorów niezależna od cache wyników; jawny kontrakt dla wygaśnięcia, fail-closed gdy nie można bezpiecznie rozstrzygnąć wcześniejszego admission; nie obiecywać nieograniczonego exactly-once na podstawie samego TTL;
- odporność na crash w każdym oknie admission/execute/commit/publish; współbieżny duplikat, uszkodzony/brakujący rejestr, błąd zapisu, restart, migracja starych danych. Nie fabrykować brakujących historycznych wpisów i nie odtwarzać historycznych tur;
- nie osłabiać owning-daemon recovery, phase-1/phase-2, ACK, MessageEnvelope, truth gate, session/turn/trace binding. Stosować kanoniczne storage i lifecycle; nie tworzyć drugiego równoległego rejestru bez przemyślanej migracji.

### F02 — P0/P1 zależnie od kontraktu — błędna/niejednoznaczna klasyfikacja awarii modelu — OBSERVED

Kontrolowany test: `FAULT_TRIGGER` 16:56:06 +01:00, n_gen=206, CTRL_BREAK_SENT=True, POST /api/chat HTTP 500; proces Ollama zakończony, port 11435 wolny. Daemon nadal ready, runtime-write ready, ten sam instance, submitted 5→6, completed bez zmiany, rejected 2→3, 0 pending. Terminalny błąd `host_finalization_contract_not_persisted`, publiczny poll `phase1_public_job_binding_unverified` i must_not_replay=true. Przy modelu offline auto bez verified bridge: null_fallback, ale analogiczne odrzucenia; core pozostaje ready.

Sprawdzić propagację błędu transportu modelu i null route przez worker/daemon/CLI. Nie zmieniać bez dowodu prawidłowej polityki odmowy; nie generować fikcyjnej odpowiedzi ani kontraktu phase-2 w celu uniknięcia błędu. Raportować właściwy cause, terminalny stan, no replay, model endpoint i liczniki; niezależnie rozliczyć circuit breaker i brak automatycznego fallbacku po przyjęciu.

### F03 — P1 / potencjalna blokada publicznego kontraktu — projekcja finalizacji CLI — OBSERVED

Lokalne tury: completed, final_visible_answer, answer_ok, canonical_persistence_ok, session_persistence_ok, integrity valid/consensus, MessageEnvelope valid. Jednocześnie CLI daemon_completion = completed_job_unverified, finalized_successfully=false, phase_result_ready=false. Rozdzielić lokalną zaakceptowaną finalizację od host phase-2. Ustalić według kanonicznego kontraktu, czy to oczekiwana ostrożna projekcja czy defekt; poprawiać tylko niespójność udowodnioną testami. Nie wymuszać finalized_successfully=true i nie nadawać głosu ChatGPT bez accepted host finalization.

### F04 — P1 — jakość/grounding i limit odpowiedzi — OBSERVED

Nowa izolowana sesja bez historii i MEMORY odpowiedziała nazwą Genesis mimo braku podstaw; nie przeniosła Mira, ale halucynowała fakt. Esej zawierał błędne twierdzenia historyczne; drugi test raportował done_reason=length, eval_count=800, prompt_eval_count=4932. Poprawna integralność techniczna nie dowodzi prawdziwości semantycznej. Zbadać politykę niepewności, pochodzenie faktów, obsługę limitu generacji i kontekstu (konfiguracja serwera 4096 vs prompt_eval_count 4932, nie wyciągać wniosku o efektywnym kontekście bez dowodu). Nie zastępować modelu sztywną odpowiedzią tylko dla testu. Nie gwarantować braku halucynacji.

### F05 — P1/P0 zależnie od skutków — response_write_error_count=5 — OBSERVED

Brak ustalonej przyczyny i korelacji z transportem. Sprawdzić logi/trace rozłączenia, broken pipe, odpowiedź HTTP, licznik i publiczny polling bez replayu. Nie zakładać utraty zapisu kanonicznego ani maskować wyjątków.

### F06 — P0 jeśli brak skutecznej mitigacji — SQLite WAL-reset — RISK

Raport runtime: SQLite 3.50.4, wal_reset_fix_available=false, deklarowana serializacja zapisów. Oficjalna dokumentacja SQLite opisuje szczególne okno współbieżnych zapisów/checkpointów. Sprawdzić wszystkie rzeczywiste połączenia/procesy, checkpointy, tryb journaling i zabezpieczenie; nie traktować deklaracji jako dowodu. Preferować wspieraną poprawioną wersję albo sprawdzoną mitigację zgodną z oficjalną dokumentacją. Nie aktualizować globalnego Pythona, prywatnej SQLite ani MEMORY w ramach tego patcha bez osobnej autoryzacji.

### F07 — P1 — procedura i preflight — CONFIRMED / ENVIRONMENT

Przykład host-preflight z --root nie jest przyjmowany przez parser tego SHA; runbook już przewiduje sprawdzenie --help i wykonanie z bieżącego katalogu. Zaktualizować przykład, nie dodawać równoległego parsera. Odtworzyć izolowane env w każdym nowym PowerShell: brak JAZN_OLLAMA_BASE_URL skutkował sprawdzaniem domyślnego 11434 zamiast 11435 i odmową przed admission (licznik bez zmiany). Odróżniać błąd procedury/środowiska od defektu runtime. Zachować konfigurację testowego magazynu modeli; nie pobierać modeli ani zmieniać produkcji bez zgody.

## 4. Implementacja i bramki wydania

1. Zachować obecny klon i lokalne artefakty; nie uruchamiać na nim nowych tur/restartów/replayów. Nie aktualizować master ani źródłowej gałęzi.
2. Przeczytać właściwe AGENTS, kontrakty finalizacji i politykę zależności. Przygotować poprawki na tej gałęzi, najpierw F01 i F02, później rozliczyć F03–F07. Oddzielić potwierdzone defekty od ryzyk/obserwacji.
3. Dodać regresje dla wszystkich stanów terminalnych, TTL, restart, crash windows, konkurencyjnego admission, błędu storage, konfliktu fingerprint/principal, migracji, kanałów CLI/JSONL/MCP/JSS i nienaruszonego phase-2. Testy duplikatów wyłącznie w nowych syntetycznych fixture/izolowanym środowisku, nie replay historycznych tur operatora. Nie usuwać ani nie osłabiać istniejących asercji.
4. Podnieść wersję przy patchu SYSTEM według AGENTS; zsynchronizować manifest i provenance wyłącznie kanonicznym release_metadata_sync. Testy celowane, pełna macierz wymaganych CI, Pyright, Windows/Ubuntu, metadata sync i readiness 16/16 na rzeczywistym kandydacie SHA. Nie deklarować wyniku przed wykonaniem.
5. Nowy katalog PC, wolne oddzielne porty, jawna konfiguracja venv, local-only Ollama, bez prywatnej MEMORY/płatnego API. Powtórzyć OR-01–OR-05 z pełnym dowodem nowych testów; rozliczyć circuit breaker OPEN/HALF_OPEN poprzez odrębne rzeczywiste awarie, nie odmowy discovery. Nie mylić testu izolacji sesji z poprawnością odpowiedzi.
6. Dokończyć kontrolowane lokalne phase-2/MCP/JSONL/host-finalize, autoryzację, odmowę przy złym hash/instance, ACK i pozostałe adaptery/egress. Pełny live ChatGPT/MCP/Cloudflare pozostaje w etapie 09 zgodnie z STAGE05_PC_ACCEPTANCE.md, chyba że kanoniczny plan zostanie jawnie zmieniony.
7. OR-06 finalny raport PASS/FAIL/BLOCKED/NOT_RUN dla każdego przypadku, z SHA, rzeczywistym dowodem i ryzykami. Dopiero po pozytywnym odbiorze odblokować etap 06. Bez merge/deploy bez osobnej zgody.

## 5. Źródła i granice

- Kod bazowy: https://github.com/SmuklyLew/jazn_latka/blob/282dc4e821ef5bf5815b4f4f7860f98c385931db/latka_jazn/core/runtime_daemon.py#L1245-L1349
- Admission: https://github.com/SmuklyLew/jazn_latka/blob/282dc4e821ef5bf5815b4f4f7860f98c385931db/latka_jazn/core/runtime_daemon.py#L2266-L2346
- Odbiór: [STAGE05_PC_ACCEPTANCE.md](STAGE05_PC_ACCEPTANCE.md).
- AWS Builders' Library — identyfikatory operacji, parametry, atomowość i późne ponowienia: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- RFC 9110 §9.2.2 — zasady ponawiania operacji nieidempotentnych: https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2
- SQLite — WAL reset bug: https://www.sqlite.org/wal.html#the_wal_reset_bug
- Ollama — Chat API: https://docs.ollama.com/api/chat

Ten dokument jest zapisem dowodów i kryteriów naprawy, nie implementacją. Naprawy SYSTEM, ich testy, ponowny odbiór i release pozostają NOT_RUN w chwili jego utworzenia.

## 6. Checkpoint audytu F01 i końcowego stopu PC (2026-11-26)

Status: **ANALYZING / RELEASE BLOCKED**. Referencyjny HEAD audytu: `aa8f9b16be7a6a84b0d5876f576aa029380c15ca`; kod runtime analizowany na tym refie, bez zmian SYSTEM. Cztery workflow dokumentacyjnego SHA `02a7d9809a5c359be44aa273cc8a86371d4651f1` zakończone success (Pyright 45869198838, release-hardening 45869198850, MCP 45869198833, memory-cloud 45869198827). Nie są dowodem napraw F01–F07.

### 6.1 F01: dodatkowe miejsca wymagające wspólnej poprawki

W [runtime_daemon.py na referencyjnym SHA](https://github.com/SmuklyLew/jazn_latka/blob/aa8f9b16be7a6a84b0d5876f576aa029380c15ca/latka_jazn/core/runtime_daemon.py) audyt statyczny wskazuje:

| Zakres | Obserwacja |
|---|---|
| 1245–1349 | Filtrowanie terminalnych zadań przy zapisie i scalaniu poprzedniego snapshotu zachowuje completed oraz szczególny failed/runtime_turn_not_accepted, lecz nie wszystkie przyjęte stany. |
| 1359–1375, 2340–2365 | Wrapper zapisu przechwytuje błędy storage i zwraca False. Admission umieszcza zadanie w kolejce przed zapisem i nie sprawdza wyniku bool; obsługa wyjątku wokół wrappera nie rozlicza zwróconego False. Ryzyko wykonania lub ACK bez trwałego admission wymaga osobnego fault-injection. |
| 1377–1543 | Recovery pomija inne terminalne stany, a uszkodzony JSON jest kwarantannowany; brak/nieprawidłowy rejestr wymaga odrębnej polityki admission, nie założenia pustej historii. |
| 1545–1556, 2266–2295, 2385–2466 | Cache TTL usuwa terminalne zadania z RAM; odczyt tombstone obsługuje tylko określone stany. Błąd odczytu, uszkodzony wpis i brak wpisu zwracają None, który ścieżka admission interpretuje jako brak istniejącego zadania. To rozbieżność z deklarowanym fail-closed. |
| 2468–2505 | Poll wykorzystuje odczyt tombstone, reconcile i owning-daemon projection recovery. Zachować autoryzację, lineage i odzyskiwanie istniejącego commita bez wykonywania nowej tury; nie rekonstruować widocznej odpowiedzi z samego tombstone. |

To potwierdzenie ścieżek statycznych i ryzyk, nie dowód wykonania replay ani nowego testu regresyjnego. Poprawka nie może ograniczać się do usunięcia jednego warunku terminalnego. Należy uzgodnić reprezentację trwałego wpisu i jednoznaczne rozróżnienie absent / found / unreadable / invalid, a następnie objąć wspólnym kontraktem admission, recovery, merge i TTL. Zachować dozwolone istniejące mechanizmy host settlement. Nie zapisywać promptów, treści odpowiedzi ani sekretów w tombstones.

Kolejność test-first: (a) wszystkie zaakceptowane terminalne statusy po restart i TTL, (b) błąd zapisu przed wykonaniem, (c) uszkodzony/brakujący rejestr po wcześniejszym admission, (d) konkurencyjny duplikat i konflikt tożsamości/fingerprintu, (e) crash przed/po durable admission oraz przed/po commit/publish, (f) wcześniejsze poprawne host-settlement i recovery. Dla każdej próby kontrolować liczbę wywołań modelu, nowych zapisów i przyjętych jobów. Wyłącznie izolowane syntetyczne fixture.

Uzasadnienie: AWS Builders' Library opisuje konieczność atomowego powiązania identyfikatora klienta z mutacją stanu; RFC 9110 §9.2.2 odradza automatyczne retry operacji nieidempotentnej bez wiedzy o jej skutku. Nie oznacza to gwarancji nieograniczonego exactly-once dla zewnętrznej inferencji; w niejednoznacznym oknie obowiązuje brak replayu. SQLite 3.50.4 użyta na PC pozostaje w zakresie WAL-reset opisanym w oficjalnej dokumentacji, poprawka w 3.51.3+ i backportach 3.50.7/3.44.6; czyste integrity_check nie dowodzi usunięcia ryzyka współbieżności.

### 6.2 Uzupełnienie dowodów PC: graceful shutdown

Operator potwierdził kanoniczny stop izolowanego daemona: `stopped=true`, `shutdown_requested=true`, `process_exit_observed=true`, `endpoint_down_observed=true`, exit 0. Ponowny status: inactive, process_state=dead, endpoint_reachable=false, runtime_core_ready=false, exit 1 zgodnie z kontraktem statusu. Niezależne sprawdzenie PID/portu zakończone DAEMON SHUTDOWN PASS. Manifest 4003 plików i source provenance OK; głęboki odczyt operacyjnych baz SQLite: audit 63, memory 58, integrity OK i 0 naruszeń FK. MEMORY pozostawała off. Odbiór dotyczy starego SHA, nie naprawionego wydania.

- F05: końcowy licznik response_write_error_count wzrósł do 6; last_response_write_error = ConnectionAbortedError (klient rozłączył się przed zapisaniem odpowiedzi). Brak przypisania konkretnego błędu do stopu lub utraty tury. Rozliczyć z logami i testem transportu.
- F08 (P2, diagnostyka lifecycle, OBSERVED): po świadomym stopie raport zawiera recommended_repair=endpoint_unreachable sugerujący ponowny stop/start, mimo stopped_daemon_runtime, nieżywego procesu i nieaktywnego endpointu. Historyczny marker ma jeszcze świeży wiek heartbeat, natomiast nie jest dowodem żywego procesu. Test ma odróżniać prawidłowy stop od awarii endpointu i nie zalecać samoczynnego uruchomienia. Nie zmieniać status exit code=1 dla nieaktywnego procesu.
- Status snapshotu może zachowywać poprzednie liczniki i stan workerów; nie interpretować ich jako bieżących po stopie. Nie usuwać markerów ani rejestrów.
- Zachować testowy klon jako dowód, nie uruchamiać nowych tur, nie restartować, nie odtwarzać historycznych requestów. Ponowny odbiór tylko w nowym katalogu po naprawie.

### 6.3 Stan środowiska implementacyjnego

GitHub API dostępne. Próba odczytu refu przez terminal Git zakończyła się błędem DNS (Could not resolve host: github.com); brak dostępnego checkout tego SHA w tej próbie. Handoff do środowiska roboczego nie został przyjęty. Nie wykonano pytest, nie zmieniono kodu runtime ani wersji i nie synchronizowano ręcznie metadanych. Lokalny worktree niezweryfikowany; limit hosta: usage_unknown. Następna bezpieczna operacja: zweryfikowany osobny checkout aktualnej gałęzi, pełny odczyt właściwych zależności/kontraktów i uruchomienie testu odtwarzającego F01 przed poprawką. Nie przechodzić do etapu 06.

## 7. Checkpoint po odzyskaniu Codexa i CI .32 (2026-11-28)

**Stage 05: WIP_NOT_ACCEPTED / RELEASE BLOCKED.** Zachowano poprawki `cda500b2fe1d3581b2d947316557734c75034282`, automatyczny katalog testów `3107bd3fae085f6089c6548211f1ded739021a13` i metadane `34159fb1114d164fd9be8d42c853d147c0b871e8`. Nie zmieniano instalacji PC ani MEMORY. Nie odtwarzano historycznych requestów. Nazwy obszarów najnowszego odbioru nie zastępują pierwotnego katalogu F01–F08.

Dowody CI `cda500b2`: 7/9 workflow success; persistent-runtime-e2e (Windows/Ubuntu) 95 passed + 1 failed na platformę (deployment .31 vs runtime .32); release-hardening Windows Stage 05 315 passed + 3 failed (canonical context rejection vs rozszerzona projekcja), Ubuntu zatrzymany na deployment_runtime_version_mismatch przed pełną regresją. Wszystkie sześć zadań dependency matrix success. Lokalna szersza regresja Codexa 581 passed, 55 failed, 11 skipped dotyczy innego zakresu; nie utożsamiać wyników. `active_degraded` na bazowej .31 i po zmianach pozostaje otwarte.

- .33: wspólne źródło bounded context refusal, zachowujące dotychczasowe pola i dodatkowe bezpieczne metadane Codexa; nie zmieniono istniejących asercji. Dodano syntetyczny test dokładnej zgodności klasyfikatorów, ograniczenia attempts i braku prywatnej treści.
- .33: kontrakt deployment wyrównany do kanonicznego PACKAGE_VERSION_FULL bez zmiany wymagań readiness, MCP lub supervision.
- Kontrole w tym środowisku: statyczny przegląd zmienianych plików i istniejących testów; wykonanie pytest i canonical metadata sync pozostają do potwierdzenia przez CI. Nie deklarować PASS dla .33 z wyników .32. Nie edytować ręcznie manifestu/provenance.
- Następne kroki: potwierdzić CI nowego SHA, porównać pozostałe regresje z .31, dokończyć fail-closed executor authority (także legacy), zachować rzeczywiste błędy adaptera, sprawdzić endpoint JSS/Monitor i audyt, niezależne dowody finalizacji, readiness oraz kontrolowane idle CPU. Pełny gate Windows/Ubuntu i niezależny odbiór PC nadal obowiązują; nie rozpoczynać Stage 06.

Źródła: https://github.com/SmuklyLew/jazn_latka/actions/runs/46176273981 ; https://github.com/SmuklyLew/jazn_latka/actions/runs/46176273832 ; https://docs.pytest.org/en/stable/how-to/assert.html ; https://docs.github.com/en/rest/guides/using-the-rest-api-to-interact-with-your-git-database .

## 8. Checkpoint .34 — executor contract convergence (2026-11-28)

**Stage 05: WIP_NOT_ACCEPTED / RELEASE BLOCKED.** Base `b033241046a9e4b1a532a26a4f96fcc3502762bc`; Codex .32 and .33 changes preserved. No local PC or private MEMORY touched. No historical request replay. Usage: usage_unknown.

Evidence at .33 implementation SHA `16b60d7799c09c23fa3157f043354bf2e638bf8f`: 8/10 workflows success; Windows Stage 05 F01–F06 318 passed; full Ubuntu suite 5112 passed, 17 failed, 28 skipped, 6 subtests passed. The 17 failures group into 12 startup version mismatches, one MEMORY E2E (also failing on Windows), one pending host restart, one legacy dialogue assertion, one bounded Ollama retry fixture, and one function-budget violation. See release-hardening run 46177740996 and persistent E2E 46177741040.

Changes in this .34 checkpoint (runtime correctness still pending CI):
- Modern result with generation-need field and missing executor evidence is not an implicit legacy host request; explicit non-host or unavailable executor remains refused. Old wire compatibility without modern generation-need field is unchanged and remains subject to further admission-authority audit.
- RecoveryPolicy extracts the bounded semantic retry block without changing candidate validation, provenance or retry count. Host request needs selected available host bridge; missing executor metadata cannot authorize it.
- E2E fixtures explicitly select the host command and route rather than expecting host generation from the null executor or a generic process job. Existing memory grounding, session reuse, lineage, pending/restart persistence and phase-2 assertions are retained. The null legacy-dialogue case now asserts both need and absence of host authority; ordinary-handler cutover and rejected persistence assertions retained. Retry fixture uses real ModelExecutorPreflight shape. Prior four test blobs archived exactly in tests/archive/v12730-10-33-before-executor-contract-migration with provenance.
- Startup contract and deployment contract aligned to .34; version source remains version.py. Canonical metadata sync is not executed locally; CI must generate manifest/provenance. No manual edit to either generated file.
- New negative modern executor regressions: missing/malformed/unavailable/local/external preflight cannot authorize a host; valid host selection still cannot bypass an incomplete phase-1 contract.
- Verification: GitHub API source/ref and static transformation only; no local pytest, compileall, or cleanroom package. Test fixtures migrated to preserve intended semantics, not to assert failure as success. All E2E/runtime results for .34 remain NOT_RUN until CI evidence.

Remaining: full executor admission/legacy compatibility audit (including conflicts between command and configured adapter), failure diagnostics across fallback/retry, root cause of active_degraded, Monitor/JSS effective endpoint/audit validation, idle CPU measurement, full regression and actual Windows acceptance. Do not mark Stage 05 accepted on fixture or CI success alone.

Sources: https://github.com/SmuklyLew/jazn_latka/actions/runs/46177740996 ; https://github.com/SmuklyLew/jazn_latka/actions/runs/46177741040 ; https://docs.pytest.org/en/stable/how-to/monkeypatch.html ; https://docs.python.org/3/library/dataclasses.html .
