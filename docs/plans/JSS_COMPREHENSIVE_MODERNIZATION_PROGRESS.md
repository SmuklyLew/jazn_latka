# JSS — kompleksowa modernizacja: plan i trwały stan

Specyfikacja użytkownika: „JAŹŃ JSS — kompleksowa modernizacja systemu i środowiska operatorskiego.md”, 2026-11-01, sekcje I–XVII (odczytane w całości).

## Stan bazowy i budżet

- Repozytorium: `SmuklyLew/jazn_latka`; checkout: `D:/.AI/jazn_latka_master`.
- Lokalny i zdalny `master`: `784f3aac8a56288cdb2e3af22e5bd1560228cd59`; drzewo przed pracą czyste.
- Wersja bazowa: `16.3.25.5.116.0.34.94.6.55`.
- Gałąź: `upgrade/jss-comprehensive-modernization`, utworzona z tej bazy.
- Oficjalny `get_usage_limits`: początkowo 2% / 5 h i 65% / tydzień; kolejny odczyt 9% / 5 h i 67% / tydzień.
- Reset 5 h: 2026-11-01 10:41:38 Europe/Warsaw; tygodnia: 2026-11-04 08:02:53 Europe/Warsaw.
- Użytkownik doprecyzował w tej sesji: progi 60/65/70% dotyczą **wyłącznie okna 5 h**. Tydzień monitorować osobno. Żadnych resetów, kredytów ani płatnych modeli.
- Prywatne/ignorowane `.settings_local`, runtime, eksporty, cache i środowiska zastane: zachowane, bez czyszczenia i bez dodawania do Git.
- GitHub connector zwrócił niedostępność narzędzia; aktualny zdalny SHA potwierdzony przez `git ls-remote`.

## Etapy i zależności

Każdy warunek poniżej wymaga dowodów na właściwym SHA. Testy celowane nie zamykają etapu. Nie przechodzić do kolejnego etapu bez wymaganej bramki poprzednika.

| Etap | Implementacja / pliki do sprawdzenia | Walidacja i warunek ukończenia | Stan |
|---|---|---|---|
| E0 | AGENTS.md, AGENTS.codex.md, ARCHITECTURE.md; istniejące katalogi Test Studio i 22 TPA; importy, entrypointy, workflow, migracje Studiów | Zapisany baseline, pełny aktywny katalog i macierz wykonawców; diagnoza luk bez duplikacji logiki | IN_PROGRESS |
| E1 (po E0) | `tpa_reports.py`, `tpa_catalog.py`, `tpa_engine.py`, `test_catalog_view.py`; trwały manifest, osobne wyniki TXT/JSON, integralność, czytnik historii | NOT_RUN widoczne; crash/recovery, read-only external history, redakcja, korupcja, SHA drift; Windows i Linux; P0 PASS | IN_PROGRESS |
| E2 (po E1) | `terminal_session.py`, `terminal_view.py`, `pty_controlling_child.py`, `operator_workspace.py`; profile, sesje i sprawdzony renderer VT | Każda dostępna powłoka, Unicode, stdin, interaktywny Python, Ctrl+C, exit/reopen, resize, ANSI/alternate buffer, kilka kart, własność i cleanup; osobne dowody P0.1 | NOT_RUN |
| E3 (po E2) | `release_metadata_sync`, generator manifestu/provenance, `.github/workflows/release-hardening.yml`; reprodukcja błędu z bazowego SHA | Zamrożone source SHA, canonical write, commit, final SHA check, idempotencja, brak pętli commitów; exact-head CI PASS | NOT_RUN |
| E4 (po E3) | `tpa_live.py`, `tpa_paths.py`, `chat.py`, `validation_worker.py`; kanoniczny runtime w oddzielnym stagingu | Windows: root/version/PID/instance/heartbeat, rzeczywisty model, dwie zaakceptowane tury, reconnect, ten sam request resume, finalizacja i własny cleanup; żadnego zastępowania live przez unit | NOT_RUN |
| E5 (po E4) | `STUDIO_MIGRATION.md`, `view_studios.py`, konfiguracja, MEMORY, rebuild, testy, generator, dependencies, Python, start, version; usługi istniejących właścicieli | Inwentaryzacja każdej funkcji, błędy/anulowanie/recovery, porównanie stary/nowy; 12 oddzielnych bramek; zachować legacy do parzystości | NOT_RUN |
| E6 (po E5) | `chat.py`, `chat_protocol.py`, `view_chat.py`, `view_events.py`; stan wielu sesji i trwały request_id | Izolacja wiadomości, restart GUI bez replay, tab switch, resume, ACK/display_exact, canonical history/export; jeden właściciel MEMORY i finalizacji | NOT_RUN |
| E7 (po E6) | shell, layout, theme, visual_system, operator_workspace i visual_ci; centralne karty/split, panele i fokus | 860×580, 1240×840, 1920×1080; DPI 100/150/200%; motywy, monitory, accessibility, rzeczywiste screenshoty i osobny manual acceptance | NOT_RUN |
| E8 (po E7) | Pełne SYSTEM/JSS/TPA, wszystkie wymagane workflow, pakiet EXE/offline, dokumentacja i instrukcje agentów | Pełna macierz Windows/Linux i live/operator, komplet dowodów, metadane deterministyczne na finalnym SHA; RELEASE_ACCEPTED tylko bez brakujących bramek | NOT_RUN |

## Ustalenia E0

- JSS ma już jeden modularny proces Qt (`view_*.py`), wspólny Controller, panel operatorski i walidowany layout. Nie wprowadzać drugiego control plane.
- `tpa_catalog.execution_map()` ma 22 scenariusze z 12 bramkami Studiów, przypisanymi regresjami oraz odrębnym pełnym odbiorem.
- `tpa_reports.RunStore` ma redakcję, atomowe compatibility reports, niezmienne rewizje, recovery i jawny eksport. Rozszerzać istniejącą logikę zamiast zastępować ją konkurencyjnym magazynem.
- Obecny `test_catalog_view.py` jest tylko czytnikiem oczekiwań; nie ma jeszcze pełnej historii wymaganej przez P0.
- Resolver lokalny obecnie autoryzuje `.settings_local/operator` (i wąski acceptance/operator), a nie dowolne `.settings_local/jazn_studio`. Preferowane miejsce specyfikacji trzeba pogodzić z tym kontraktem; nie dodawać szerokiego wyjątku bezpieczeństwa.
- Nie potwierdzono jeszcze pełnej parzystości, interaktywnej emulacji VT, finalnego release-hardening ani live acceptance. Obecność modułów nie jest dowodem tych bramek.

## Raporty i testy

Lokalne dowody tej sesji: `D:/.AI/codex_tasks/jss-modernization-20261101/evidence/`.
Pełne SYSTEM/JSS/CI/TPA/live i finalny release gate: **NOT_RUN** do czasu zapisania rzeczywistych wyników.

## Najbliższy krok

Sprawdzić oficjalne wykorzystanie 5 h, używać rzeczywistego absolutnego interpretera (alias `python` wskazuje na Windows Python Install Manager), wykonać i zachować baseline celowanych testów TPA. Następnie wdrożyć manifest i osobne raporty w istniejącym RunStore, czytnik integralności i historię Qt. Nie rozpoczynać E2 przed P0 PASS.

## Checkpoint implementacji E0/E1 — 2026-11-01

Wdrożono fundament, nie zamknięto P0. RunStore ma niezmienny manifest i jawny zewnętrzny katalog dowodów. Nowy `test_evidence_archive.py` tworzy osobne TXT/JSON wszystkich wymaganych pozycji, kompletne snapshoty, SHA-256 i bezpieczny import/eksport ZIP. Odmawia zmiany manifestu i przeniesienia wykonanego wyniku na inne źródło. `test_history_view.py` daje asynchroniczny odczyt/import/eksport, filtry, porównanie przebiegów, ostatni sukces/porażkę i podgląd TXT/JSON/JUnit/logów. `test_evidence_plugin.py` jest adapterem istniejącego pytest: rejestruje zebrane parametryzacje, niezebrane aktywne definicje, 22 TPA i bramki terminali/GUI/platform/release. Setup/call/teardown mają niezmienne potwierdzenia. Błąd teardown lub kolekcji nie staje się PASS.

`tpa_view.py` ma teraz rozwijane klawiaturą zaawansowane filtry: kolejka mieści się w oknie 860×580, wyszukiwarka pozostaje widoczna. Podniesiono wersję SYSTEM i zgodne pola startup/deployment, katalog testów generuje kanoniczny synchronizator. Manifest/provenance generować z zatwierdzonego źródła. Workflow JSS zawiera nowe testy i JUnit upload na każdym wyniku; przypięty upstream action.yml potwierdza node24. Audyt 23 workflow: PASS.

Wyniki kolejnych przebiegów (nie sumować powtórzeń), raporty TXT/JUnit w `evidence/` katalogu zadania:

| Przebieg | Wynik | Pliki |
|---|---|---|
| Baseline TPA | 22 PASS | `baseline-tpa.*` |
| Pierwszy patch danych | 39 PASS, 1 SKIPPED (symlink capability) | `e1-data-first.*` |
| Dane + Qt | 43 PASS, 1 SKIPPED | `e1-data-qt.*` |
| Import ZIP + historia + istniejący katalog Qt | 30 PASS, 1 SKIPPED | `e1-import-qt.*` |
| Szersza TPA w ograniczonym procesie | 184 PASS, 9 FAIL, 2 SKIPPED | `e1-regression.*` |
| Ponowienie Git/junction na właściwym wykonawcy | 50 PASS, 1 FAIL (kompaktowy układ) | `e1-failures-native.*` |
| Stary katalog z master w procesie testowym (nie pełny baseline master) | 1 FAIL (ten sam układ) | `baseline-compact.*` |
| Poprawa układu bez zmiany istniejącej asercji | 4 PASS | `compact-fixed.*` |
| Adapter na rzeczywistym syntetycznym projekcie, przed dodatkowym testem częściowej kolekcji | 2 PASS | `e1-plugin-fixed.*` |
| Typy zmienionych modułów i nowych testów | PASS, 0 errors/warnings | `e1-types-checkpoint.txt` |
| Pierwsza pełna próba SYSTEM/JSS | 9 ERROR kolekcji, 2 SKIPPED, wykonanie przerwane | `full-system-jss.*` |

Pierwsza pełna próba wyłączyła autoload pluginów bez jawnego AnyIO; brakowało też httpx. To nie jest PASS suite. Manifest 3772 pozycji i dowody zachowano w `registered-full-run/run-171d559cf40f4fb3bbd0588ea205f66e/`. Oddzielne `venv/` zadania czyta zależności poprzedniego testowego venv i bazowego Pythona, ale instaluje nowe pakiety tylko u siebie. `httpx` zainstalowano w tym środowisku; raport z hashami: `evidence/httpx-install.json`. Ponowienie pełnej suite wymaga jawnego `-p anyio.pytest_plugin`.

Ostatni odczyt przy tym checkpoincie: 42% wykorzystania 5 h (58% pozostało, 23 punkty do STOP), tydzień 72%. Odświeżyć przed kolejnymi kosztownymi krokami.

Pozostałe E1: pełna walidacja Windows/Linux i wymaganych CI na końcowym SHA, indeks/paginacja pełnej historii, odtwarzanie częściowych potwierdzeń do GUI oraz pomiar/przeniesienie synchronicznego zapisu TPA poza GUI. Release/live/operator pozostają RELEASE_NOT_ACCEPTED. E2–E8 nie rozpoczęte.
