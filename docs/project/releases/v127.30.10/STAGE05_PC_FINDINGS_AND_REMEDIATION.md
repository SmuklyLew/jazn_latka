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
