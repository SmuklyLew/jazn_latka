# Jaźń V104 → V114 — kontrola luk i przygotowanie odbioru Windows TPA (2026-11-09)

> **STATUS: AUDIT / TPA PREPARATION; NOT RELEASE-READY; NO MASTER MERGE.**
>
> Ten dokument jest punktem kontrolnym, nie raportem wykonania testów ani dowodem gotowości runtime. Nie zmienia istniejących 22 scenariuszy TPA, wyników operatora ani chronionego stanu Jaźni/MEMORY.

## 1. Rewizje i zasady

- Repozytorium: `SmuklyLew/jazn_latka`.
- Baza: `fix/v114-main-jss-runtime-recovery-20261108`, HEAD `6f744dd74bb641cebe1b861294622a62ae49599d`.
- Referencja V104: `fix/v104-jss-daemon-diagnostics-status-hydration-20261105`, HEAD `b98ff9599e2f7d6f75d4528d3baa0e935993735c`.
- `master` w chwili porównania: `5adef1d6e3c911f9ccd0bf884b32c0364c866481`.
- V114: 176 commitów przed `master`, 0 za nim, 123 ścieżki zmienione wobec `master`.
- V104 i V114 są rozgałęzione od `master`; proste scalenie V104 w całości jest zabronione do czasu per-hunk triage.
- Linia `integrate/...105...` oraz `repair/v111...` i `repair/v114...` jest przodkiem V114. Nie należy scalać jej ponownie.
- Porównanie drzew wykazało 91 ścieżek zmienionych przez V104, których V114 nie zmienia wobec `master`; to **kandydaci do audytu**, a nie automatycznie 91 brakujących funkcji.
- Każde przeniesienie poprawki: przeczytać cały plik docelowy i zależności, zachować aktualny kontrakt V114, uruchomić celowane testy, podnieść wersję SYSTEM i wykonać **kanoniczny** `release_metadata_sync`. Manifestów i provenance nie redagować ręcznie.

## 2. Potwierdzone luki / rozstrzygnięcia przed zmianą kodu

| Priorytet | Ścieżka V104 różna od V114 | Wstępne rozstrzygnięcie / wymaganie | Dowód potrzebny do zamknięcia |
|---|---|---|---|
| P0 | `latka_jazn/mcp/http_tasks_bridge.py` | V104 nie fabrykuje `http.disconnect` po jednorazowym odczycie zbuforowanego body, ale przekazuje kolejne `receive()`; V114 ma tu dokładnie kod `master`. Rozważyć selektywny port, nie maskować prawdziwego rozłączenia. | Test rzeczywistego ASGI POST/body, dłużej trwającego JSON/SSE oraz rzeczywistego disconnect, bez podwójnego przyjęcia tury. |
| P0 | `latka_jazn/mcp/task_resume.py` | V104 używa centralnej `connect_runtime_writable` zamiast lokalnego otwierania SQLite; V114 nie dotknął tego pliku. Wymaga triage względem istniejącej polityki WAL i trwałego task ledger. | Test regresji SQLite/WAL/task resume, `BEGIN IMMEDIATE`, wersji SQLite i niemożności ponownego submit. |
| P0 | `latka_jazn/memory/html_memory_ingest.py` i `latka_jazn/tools/memory_rebuild_app/unified_core.py` | V104 kieruje zapisy/odczyty przez centralne połączenia SQLite. Ocenić czy wszystkie dotknięte entrypointy V114 wymagają tego samego fail-closed policy. | Testy źródeł syntetycznych, read-only, existing-WAL refusal i braku zmian prywatnej MEMORY. |
| P1 | `latka_jazn/core/host_finalization_transaction.py` | V104 dodaje mapowanie `voice_perspective_mismatch` na instrukcję żeńskiej narracji. Nie przenosić bez sprawdzenia nowszego walidatora V114. | Test błędnej pierwszej osoby, cytatów i jednej zaakceptowanej finalizacji. |
| P1 | `tools/jazn_run_studio/probes.py` + `tpa_live.py` | V104 umożliwia zatwierdzony lokalny `api_base` Ollamy bez wymuszania domyślnego portu. V114 zachował `master` w tych plikach. | TPA z izolowanym adresem loopback, odmowa zewnętrznych endpointów, brak ingerencji w produkcyjną Ollamę. |
| P1 | `tools/jazn_run_studio/status_summary.py` | V104 dodaje `inactive_confirmed` tylko przy zgodnej schema, nieaktywnym supervisorze, martwym PID i `not_alive`; V114 jest identyczny z `master`. | Test negatywny statusów supervisor, bez fałszywej gotowości. |
| P1 | `latka_jazn/nlp/dialogue_intent_classifier.py`, `core/route_registry.py`, `core/handlers/time_awareness_handler.py`, `core/model_guided_response_synthesizer.py` | V104 uzupełnia polskie warianty pytania o czas i kierowanie do `current_time_question`. Zbadać zgodność z nowszym routingiem oraz źródłem czasu, nie wymuszać odpowiedzi z modelowej pamięci. | Test konkretnych polskich fraz, czasu Europe/Warsaw i poprawnej ścieżki handlera. |
| P1 | `latka_jazn/tools/safe_paths.py` | V104 dodaje `SafePathRoot` z przypiętym root oraz ponowną kontrolą każdego elementu. Weryfikować zastosowania, traversal, linki i TOCTOU. | Test odmowy symlinków/junctionów i ścieżek poza root. |
| P2 | `latka_jazn/tools/dependency_studio.py` | V104 udostępnia wybór layout project/managed; V114 ma własny `tools/jazn_setup.py` i aktualne API Dependency Studio. Nie przywracać starszego parsera bez porównania kontraktów. | Test idempotencji install, rollback, zgodności ABI i `ROOT/.venv`. |
| P2 | `latka_jazn/tools/version_consistency_audit.py` | V104 ma dodatkowy wyjątek zakresowy dla pól `system_version/package_version` kontraktu Test Studio. Upewnić się, czy generator V114 nie potrzebuje tej polityki. | Audit wersji i manifestów, bez rozluźniania pozostałych literałów. |
| P2 | Pozostałe różnice w `tests/`, `docs/`, `.github/`, `tools/jazn_run_studio/` | Ocena per test/ścieżka; nie wolno kasować lub nadpisywać testów archiwalnych ani kopiować starych, nieaktualnych snapshotów. | Macierz aktywnych testów, ich archiwalnych poprzedników, testów brakujących i zachowanego kontraktu. |

Potwierdzenia powyższych różnic pochodzą z bezpośredniego odczytu plików GitHub na V104 i V114; brakujący hunk nie oznacza jeszcze brakującego zachowania, dopóki nie sprawdzono całego przepływu.

## 3. Źródła techniczne i decyzje fail-closed

- ASGI HTTP: https://asgi.readthedocs.io/en/stable/specs/www.html — `http.disconnect` to realne zdarzenie utraty połączenia, nie syntetyczny koniec bufora request body.
- MCP 2026-07-28: https://blog.modelcontextprotocol.io/posts/2026-07-28/ — transport request-scoped i jawna obsługa zadań, osobna tożsamość aplikacji.
- SQLite: https://www.sqlite.org/wal.html — WAL-reset bug oraz poprawione wydania 3.51.3, 3.50.7, 3.44.6. Wymagana kontrola **biblioteki faktycznie połączonej z Pythonem**, nie samej wersji Python.
- Windows SCM: https://learn.microsoft.com/en-us/windows/win32/services/service-status-transitions — dowód stanu procesu i poprawne zmiany stanów usługi.
- CI HEAD: https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks — wymagane kontrole na właściwym SHA.
- Operacyjny kontrakt projektu: `AGENTS.md`, `AGENTS.codex.md`, `docs/uiux/JSS_TEST_EVIDENCE_ARCHIVE.md`, `docs/project/TPA_WINDOWS_V105_V106_ACCEPTANCE.md`.

## 4. TPA Windows — katalog 22 przypadków do wykonania, nie wyniki

W `tools/jazn_run_studio/tpa_catalog.py` istnieje dokładnie 22 mapowań `REGRESSIONS`, ich `PROCEDURES` i `WINDOWS_V105_CHECKS`. Wszystkie 22 wskazane ścieżki testów zostały znalezione na V114. To **gotowość inwentarza**, nie zaliczony odbiór.

| ID | Regression fixture | Dowód operatorski |
|---|---|---|
| gui-daemon | `test_jazn_run_studio_daemon_routing.py` | Prywatny ROOT, preflight, heartbeat, endpoint, cleanup |
| ollama-two-turns | `test_jazn_run_studio_chat_contract.py` | Dwie zaakceptowane tury Ollama, role, lineage, zapis |
| chat-reconnect | `test_jazn_run_studio_reconnect_acceptance_qt.py` | Jedna sesja po ponownym połączeniu, bez duplikatów |
| chat-resume | `test_jazn_run_studio_delivery_ack.py` | Ten sam request ID, jeden ACK po finalnym wyświetleniu |
| daemon-restart | `test_heart_system_public_restart.py` | Restart wyłącznie własnego daemona, niezmieniona sesja |
| smoke-isolation | `test_package_smoke_workspace_isolation.py` | SHA chronionych markerów i MEMORY przed/po |
| config-persistence | `test_jazn_system_root_config.py` | Save/reload profilu wyłącznie izolowanego ROOT |
| studios-parity | `test_jazn_run_studio_12_manual_studio_gates.py` | Dwanaście osobnych pełnych potwierdzeń studio-* |
| offline-exe | `test_jazn_run_studio_bundle_integrity.py` | Offline VM, verified wheelhouse, JSS EXE i provenance |
| ui-accessibility | `test_jazn_run_studio_workbench_qt.py` | DPI 100/150/200%, 860x580, klawiatura, fokus |
| studio-system | `test_jazn_operator_studio.py` | Wersja, manifest, provenance, odmowa obcego ROOT |
| studio-start | `test_jazn_start_studio_dashboard.py` | Python/Ollama/daemon; port i PID to nie readiness |
| studio-configuration | `test_jazn_run_studio_configuration_native_qt.py` | Preview, save/reload, CAS i unsaved edits |
| studio-memory | `test_memory_studio_step_workflows.py` | Syntetyczna baza, role i źródła, brak prywatnych danych |
| studio-memory-rebuild | `test_memory_rebuild_p0_studio.py` | Syntetyczny plan/validate/cancel/export |
| studio-test-studio | `test_tests_studio_run_history_p1.py` | JUnit/JSON/TXT, anulowanie, historia SHA |
| studio-generator | `test_jazn_pack_generator_studio_portability.py` | Plan/ZIP/split/join, odmowa błędnej części |
| studio-dependencies | `test_dependency_studio_repeated_profiles.py` | Hash-lock wheelhouse, offline install, pip check/import |
| studio-python-runtime | `test_jazn_run_studio_integrations.py` | CPython 3.14 i ABI, wersja rzeczywistego interpretera |
| studio-version-rebuild | `test_jazn_run_studio_version_native_qt.py` | AST, canonical sync, preview, backup, rollback |
| studio-chat-import | `test_memory_studio_step_workflows.py` | Synthetic import, dedup, verification i search |
| studio-memory-restore | `test_memory_restore_tool.py` | Synthetic baseline/scan/compare/backup/restore |

Wszystkie pliki powyżej znajdują się w `tests/`. Stan odbioru **każdego** scenariusza dla nowego HEAD: **NOT_RUN**, dopóki kanoniczny TPA RunStore nie zwróci podpisanej tożsamości źródła i trwałych dowodów wykonania. Gdy brakuje modelu, wheelhouse, GUI, uprawnień, platformy albo dostępu — `BLOCKED` z konkretnym powodem. Nie promować pytest PASS do `full_gate PASS`.

### Kolejność bezpiecznego wykonania na Windows (operator)

1. Zweryfikować świeży, izolowany SYSTEM i pełny HEAD/SHA; nie używać aktywnego V74 ani MEMORY.
2. W JSS wybrać **TPA — Testy przepuszczania aktualizacji**, sprawdzić read-only preflight, spis wszystkich 22 ID i powiązania `scenario` → `REGRESSIONS` → `PROCEDURES` → `WINDOWS_V105_CHECKS`.
3. Wybrać nowy katalog operatora, workspace, port i modele; zweryfikować własny Python 3.14 / `.venv`, wheelhouse oraz `/api/tags` i rzeczywistą generację Ollamy. Braki udokumentować jako `BLOCKED`, nie pobierać nic podczas rozmowy.
4. Najpierw scenariusze izolacji, manifestów, negatywnych odmów i SQLite; potem `gui-daemon`, `ollama-two-turns`, `chat-reconnect`, `chat-resume`, `daemon-restart`; wreszcie wszystkie 12 `studio-*`, `offline-exe` i `ui-accessibility`.
5. Z każdego scenariusza odczytać **własne** `execution_status`, `full_gate`, `case_id`, `source_commit`, wersję, log z redakcją sekretów, raporty TXT/JSON/JUnit, stan cleanup. Każde archiwum zachować append-only.
6. Potwierdzić 22/22 przypadki o pełnym `full_gate PASS` dla **identycznego SHA**; gdy choć jeden jest `NOT_RUN`, `BLOCKED`, `FAIL` lub `NIEAKTUALNE`, odbiór końcowy pozostaje otwarty.

Dodatkowe wymagania: rzeczywiste Windows 10/11 x64, niezależna maszyna/VM offline dla `offline-exe`, DPI i dostępność przy natywnym Qt, realne `Ollama /api/chat` z `done:true`, bez ręcznej ingerencji w prywatną bazę.

## 5. Wymagane bramki CI i stan dowodów

W dostarczonym przez operatora wykazie `gh run list`, na V114 HEAD `6f744dd` występują 4 zielone przebiegi: `pyright-active-tree-audit`, `memory-cloud optional capability release gate`, `MCP 2026-07-28 conformance release gate` oraz `release-hardening`. Poprzednie zielone `persistent-runtime-e2e` dotyczą starszego SHA.

Przed końcowym PR do master:
- zamknąć wszystkie pozycje P0/P1 audytu albo zapisać precyzyjne, testowalne wyjaśnienie, dlaczego zmiana V104 jest niepotrzebna;
- na nowej gałęzi wykonać selektywne poprawki, aktywne regresje i archiwizację zmienionych testów;
- z użyciem rzeczywistego executora uruchomić `python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json`, ponowną weryfikację/idempotencję i commit wersji;
- wywołać pełne wymagane CI na **jednym finalnym SHA**, a wszystkie błędy/skip/unavailable przeanalizować bez udawania PASS;
- zakończyć 22/22 odbiorów TPA na Windows z trwałym kompletem dowodów i odrębną próbą ChatGPT-MCP, jeśli zakres wydania ma potwierdzać publiczny ingress;
- dopiero wtedy utworzyć końcowy PR do `master` (bez automatycznego merge).

### Stan bieżącego checkpointu

- [x] Wstępny audyt różnic V104/V114, priorytety i źródła.
- [x] Zweryfikowane istnienie 22/22 plików testowych wskazanych przez aktualny TPA.
- [ ] Port potrzebnych hunków V104 do nowego SYSTEM + nowa wersja i kanoniczne metadane.
- [ ] Lokalne testy nowych zmian; pełne CI na finalnym HEAD.
- [ ] Rzeczywiste 22/22 Windows TPA z pełnymi dowodami.
- [ ] Zatwierdzenie finalnego PR do master.

**Brak lokalnego checkoutu HEAD V114 i dostępu DNS do github.com w executorze tej sesji; dostęp przez połączone GitHub API pozwala na inspekcję i dokumentacyjny checkpoint, ale nie zastępuje kanonicznego wydaniowego sync/testów ani odbioru Windows.** Nie odnotowano jako PASS żadnej niewykonanej próby.

`usage_unknown` — host nie udostępnia wiarygodnego licznika zużycia pięciogodzinnego limitu.
