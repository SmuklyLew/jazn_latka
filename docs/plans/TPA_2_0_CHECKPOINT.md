# TPA 2.0 — checkpoint

## Aktualizacja 2026-10-30 — naprawa 4 nieudanych checków Windows

- Sprawdzono rzeczywiste logi dla PR #443 / SHA `ecd2536e1747030d4dde8f7edc25fb3f4636681c`:
  trzy zadania `jazn-run-studio` (Windows Python 3.12/3.13/3.14) zawiodły na
  `test_minimum_window_exposes_queue_and_expandable_setup_from_keyboard`:
  tabela TPA y=317, wymagane y<303 przy oknie 860×580.
  Osobny `powershell-terminal-regressions` wykazał błąd w
  `test_two_processes_cannot_both_commit_stale_none`: [0,1] zamiast [0,9];
  proces potomny otrzymał `Local settings path resolves outside its root`.
- Poprawiono układ TPA, przenosząc przełącznik zgody na live do istniejącego
  wiersza akcji, bez zmiany wymaganego progu testu i bez automatycznego live.
- Poprawiono `verify_local_descendant()` w `local_settings_layout.py`:
  porównanie ścieżki docelowej i root odbywa się teraz po `resolve()` obu
  stron. Nadal obowiązuje sprawdzenie każdego komponentu na symlink/junction.
  Dodano 3 syntetyczne testy porównania ścieżek i odmowy przekierowania.
- Kod i kontrakty wydania są na wersji
  `16.3.25.5.116.0.34.94.6.48-tpa-windows-ci-repair`.
  Te zmiany **wymagają CI końcowego SHA**; w chwili wpisu nie jest ono
  potwierdzone. Kanoniczna synchronizacja manifestu i provenance pozostaje
  do wykonania, bez ręcznego tworzenia hashy.
- Rzeczywiste tury Ollamy nadal dopiero po merge. PR pozostaje Draft.


## Aktualizacja 2026-10-30 — naprawa CI i rozdział odbiorów przed/po merge

- Wysłano poprawkę P2: `PlanStore` wiąże checkpoint z SYSTEM przez
  niejawny SHA-256 kanonicznej ścieżki, nie przez niezamaskowaną ścieżkę.
  Redagowanie wartości operatora nie modyfikuje strukturalnych pól
  `schema`, `plan_id`, `source_request.kind`, identyfikatorów i zależności kroków.
  Starsze, prawidłowe checkpointy z pełną ścieżką nadal są czytane dla
  zgodnego SYSTEM; nie akceptuje się checkpointu z innym rootem.
- Dodano cztery **syntetyczne** testy regresyjne kolizji sekretów, uszkodzenia
  identyfikatora SYSTEM, poufnych notatek i odczytu starszego formatu.
  Samo dodanie testów nie dowodzi PASS. Poprzedni job Windows miał 2 FAIL
  w `tests/test_tpa_2_execution_plan.py`; wymaga ponownego, rzeczywistego CI.
- Wersja kodu patcha: `16.3.25.5.116.0.34.94.6.47-tpa-checkpoint-redaction-integrity`.
  Wersję powiązano ze startup i deployment contract. Finalna synchronizacja
  `SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json` wymaga
  kanonicznego generatora; **nie wolno ręcznie fabrykować hashy**.
- Na decyzję użytkownika rzeczywisty test **co najmniej dwóch tur Ollama** oraz
  dalsze odbiory zależne od prawdziwego modelu/daemona wykonuje się
  **po merge**. Przed merge należy skończyć kreator P3 i uzyskać możliwe
  regresje/CI; odroczone odbiory pozostają NOT_RUN, nie PASS.
- Patch jest stanem rozwojowym Draft PR, nie zielonym release i nie upoważnia
  do merge. Pamięć prywatna, aktywny runtime oraz daemon pozostają nietknięte.
- Dodano P3 w kodzie: sekwencyjny kreator 17 odbiorów bez live (lub 22
  po jawnym włączeniu), skróty Ctrl+Alt+P/N, wyświetlanie postępu i
  powrót do pierwszego scenariusza bez aktualnego, zweryfikowanego
  `full PASS`. Przechodzenie między krokami nie nadaje PASS.
  Dołączanie dowodów, ich SHA-256, lista potwierdzeń i walidacja źródła
  pozostają w istniejącym `record_observation`.
- Domyślne `Uruchom plan automatyczny` zapisuje teraz wyłącznie 22
  regresje i **nie uruchamia Ollama/daemona**. Realne kroki live wymagają
  jawnego zaznaczenia przełącznika oraz wyboru zainstalowanego modelu.
  Dodano osobne testy regresji, fałszowania checkpointu, kolejki kreatora
  i Qt offscreen; wynik testów pozostaje NOT_RUN do uzyskania CI.
- Zakres P3 jest **zaimplementowany, lecz nieodebrany**: kontrola klawiatury,
  ergonomii, skalowania DPI, Windows/EXE i ponownego otwarcia na realnym
  GUI wymaga oddzielnych dowodów. Brak potwierdzenia nie jest sukcesem.


## A. Tożsamość

**P0–P2 wdrożone; kod kreatora P3 dodany, lecz nieodebrany; cały TPA 2.0 NIEUKOŃCZONY.**
Brakuje zweryfikowanego CI i rzeczywistych odbiorów opisanych poniżej. Kończymy nowe
funkcje w celu zachowania rezerwy budżetu. Ostatni odczyt: 63% puli 300 minut,
64% tygodnia. Nie utożsamiać tych wartości z limitem następnej sesji.

- Repozytorium: SmuklyLew/jazn_latka.
- Branch: `latka_work/tpa-2-auto-acceptance-history`.
- Worktree: `D:\.AI\jazn_branchs\tpa-2-auto-acceptance-history`.
- Baza: `origin/master`, `55948d3813664923ae64c6e24f345369632a1b24` (fetch wykonany).
- HEAD: commit zawierający ten checkpoint; odczytaj `git rev-parse HEAD`.
  Nie wpisujemy samoodnoszącego się SHA do zawartości commita.
- Wersja obecnego kodu: `16.3.25.5.116.0.34.94.6.47-tpa-checkpoint-redaction-integrity`.
- Data: 2026-10-30 (Europe/Warsaw).

## B. Prace i mapa modułów

Etap III / P2: dodano `tpa_execution_plan.py` i `tpa_plan_runner.py`.
Plan najpierw wykonuje regresje, potem kolejno gui-daemon → ollama-two-turns →
chat-reconnect → chat-resume → daemon-restart. Wymaga PASS zależności z kompletnymi
dowodami. Późniejsze kroki kopiują przypięte źródło pierwszego przebiegu, bez
ponownego wyboru ruchomego master. Checkpointy planu są append-only; GUI ma
„Uruchom plan automatyczny”, „Kontynuuj przerwany plan” i „Zapisz checkpoint”.
Wznowienie ponownie sprawdza zapisane dowody. Nierozstrzygnięty krok live staje
się INTERRUPTED, nigdy nowym send; dalsze zależne kroki są BLOCKED.
To bezpieczne wznowienie planu, nie automatyczne rozstrzygnięcie przerwanej tury.

Fazy mają oddzielne limity preflight/source/start/heartbeat/readiness/generation/
finalization/restart/cleanup/gui. Czekanie operatora po otwarciu izolowanego
Studio wyłącza timeout GUI; nie jest timeoutem daemona. ACK wyświetlenia ma
osobny limit i jest zapisywany w dowodach. Sterowanie nadal należy do istniejącego
Controller/ChatClient i run.py → main.py. Pomocnik live pochodzi ze Studio,
a kanoniczne run.py i testowany runtime z wybranej izolowanej kopii.

Utwardzono odbiór: Studio asynchronicznie sprawdza SHA/integralność faktycznie
testowanej kopii przed zapisem obserwacji, zamiast wymagać wersji instalacji
operatora. PASS wymaga poprawnego JUnit lub kompletnego dowodu live (tożsamość,
zaakceptowane tury, ACK, oryginalne przyjęcie request_id, nowa tożsamość restartu).
Pełny odbiór 12 studiów ponownie weryfikuje ich dowody. Późniejsza obserwacja
BLOCKED zachowuje poprzedni zweryfikowany pełny sukces w historii.
W lokalnych eksportach porównuje się hashe wszystkich chronionych plików i
provenance; czas wygenerowania nowego manifestu sam nie unieważnia identycznego
kodu. Oryginały zmienionych testów zachowano append-only z SHA256/provenance.

Etap IV / P3 pozostaje NIEUKOŃCZONY: dostępny istniejący odbiór wspomagany
z checklistą i dowodami, brak nowego kreatora prowadzącego kolejno przez wszystkie
scenariusze i niezbędne potwierdzenia. Nie deklarować całego TPA 2.0 jako gotowego.

Checkpoint etapu I został wypchnięty i zweryfikowany na GitHub:
`d79c2473839f76d88a59e6f2af5c9728a817ee70` (kod),
`c1e177da4aad741c413b00e6820743efd64af33d` (metadane).
Draft PR: https://github.com/SmuklyLew/jazn_latka/pull/443 (base master).
Etap II wypchnięty jako `13bd41bd` (kod) / `0cfd879bc8d67a4f66d6ab1a79eb650bbeacda6f`
(metadane); potwierdzono zgodność lokalnego i zdalnego SHA.
Integracja CI .45: `88cd8639` (kod) / `b2b205cfae14fda4a037503b6b1c682be1520441`
(metadane), również wypchnięte i potwierdzone.
Etap III .46: `d4ff35b23178a070d26cf80b6218455f3264ed09` (kod) /
`a9972b164256eaa3b513011c9f69103cf31c1170` (metadane), wypchnięte; lokalny
i zdalny SHA sprawdzone jako zgodne. Następne commity obejmują raport checkpointu
i jego kanoniczne metadane, bez zmian kodu wykonawczego.

Naprawy integracyjne po odczycie rzeczywistego CI etapu I: zaktualizowano
runtime_version kontraktu wdrożenia i version kontraktu startowego, wygenerowano
kanoniczny katalog testów. POSIX pty_controlling_child importuje fcntl/termios
wyłącznie na POSIX i jawnie odmawia startu na Windows; to usuwa zastany błąd
typów Windows bez wyłączenia gate'u i bez zmiany sterowania daemonem.

Etap II / P1: `tpa_sources.py` przygotowuje master/branch/PR/server merge-ref
jako osobny detached worktree. Lokalny Git musi być czysty; eksport/ZIP
wymaga kanonicznej weryfikacji pełnego manifestu i provenance. ZIP jest
ograniczony rozmiarem/liczbą plików i odrzuca dowiązania, traversal, ADS,
prywatne ścieżki oraz nazwy zmienione przez normalizację Windows.
`tpa_engine.py` przygotowuje źródło asynchronicznie przed testami, zapisuje
SHA, tree, wersję i execution_root; odmowa źródła blokuje testy bez fallbacku
na aktywny katalog. `tpa_view.py` udostępnia wybór źródła w zwijanej sekcji,
domyślnie master dla Git i zweryfikowany lokalny SYSTEM dla eksportu.
Bezpośrednie legacy API wykonawcy pozostaje kompatybilne z syntetycznymi
fixture'ami bez pakietu; publiczne Studio weryfikuje rzeczywisty SYSTEM.
Kopie kodu są zachowywane poza runtime, nie usuwane automatycznie; można
obejrzeć właściciela i dowody bez przejmowania produkcyjnych procesów.
Nowe testy: `test_tpa_2_sources.py`, `test_tpa_2_source_execution_qt.py`.
Zmiana starszego testu historii dodaje asercję non-None dla Pyright; oryginał
zachowano bajt w bajt z provenance pod tests/archive/v16.3.25.5.116.0.34.94.6.43-before-tpa-source-typing/.

Etap I / P0: wdrożony stan zbiorczy wszystkich 22 scenariuszy, niezależne kanały
regresja/live/pełny odbiór, ostatnia próba i ostatni potwierdzony sukces,
aktualność SHA/wersji oraz weryfikacja JUnit i hashy dowodów operatora.
Historyczny PASS bez materiału nie jest wyświetlany jako potwierdzony sukces.
Późniejsze NOT_RUN nie przesłania starszej próby. Regresja nie promuje full_gate.

- `tpa_current_state.py`: nowa projekcja odczytowa, odbudowywana z raportów.
- `tpa_reports.py`: niezmienne, redagowane `revision-*.json`, flush/fsync przed
  zamianą `report.json`/`report.txt`; jawne odzyskanie z kompletnych rewizji
  zachowuje uszkodzone oryginały pod unikalnymi nazwami.
- `tpa_view.py`: domyślnie stan zbiorczy; osobny zakres historii run_id;
  7 kolumn; odzyskanie wybranego uszkodzonego raportu; nie zmienia lifecycle.
- Nowe testy: `test_tpa_2_current_state.py`, `test_tpa_2_history_qt.py`.
- `latka_jazn/version.py`: podniesienie wersji; metadane wyłącznie generatorem.
- Plan: `docs/plans/TPA_2_0_IMPLEMENTATION_PLAN.md`.

Przeczytano pełne AGENTS.md, AGENTS.codex.md, referencję operacyjną i politykę
struktury/deps oraz moduły reports/triage/guidance/view/catalog/engine/paths,
release_identity i local_acceptance. Nie trzeba ponownie badać całego repo.
Nie zmieniono istniejących testów ani historycznych snapshotów.
Rewizje są dziennikiem pojedynczego przebiegu; indeks nie jest źródłem prawdy.
Oryginalne ręczne wyniki v1 pozostają w istniejącym „Starsze wyniki” i nie są
promowane do automatycznych wyników v2. Nie wymyślono migracji nieznanych schematów.

## C. Walidacja

### Końcowe dowody kodu .46

- **PASS: 149 passed, 1 skipped**, 67.68 s, TPA_EXIT=0, wszystkie aktywne
  `test_jazn_tpa*.py` i `test_tpa_2*.py`, bez tests/archive. JUnit:
  `D:\.AI\codex_tasks\tpa-2-committed-stage3-junit.xml`.
  Wywołanie: jawny QApplication(offscreen), pytest -q <pliki> --tb=short,
  własny --basetemp; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1.
- **PASS: Pyright Studio, 0 errors, 0 warnings**; osobno sprawdzono nowe testy.
- **PASS: compileall aktywnego drzewa**, z wykluczeniem historycznego archive.
- **PASS: doctor --json**, exit 0, ok=true; własny runtime/operator/MEMORY off.
  Nie oznacza gotowości rozmowy ani uruchomionego daemona: system_fully_ready
  pozostawało false w izolowanej diagnostyce. Raport:
  `D:\.AI\codex_tasks\tpa-2-final-doctor.json`.
- **PASS: package-smoke --profile system**, 15/15 kontroli, exit 0, ok=true.
  Raport: `D:\.AI\codex_tasks\tpa-2-system-smoke.json`.
- **PASS: niezależny metadata --check** dla a9972b16: synchronized=true,
  manifest_matches=true, provenance_matches=true, source_commit=d4ff35b2.
  Raport: `D:\.AI\codex_tasks\tpa-2-stage3-metadata-check.json`.
- **PASS: docs_truth_audit i sync_contract_catalog --check**.
- Pierwsza próba szerszej regresji: **FAIL, 10 failed, 578 passed, 4 skipped**,
  zatrzymana przez --maxfail=10 po 26.45 s. 8 awarii: brak jawnie załadowanego
  anyio.pytest_plugin przy wyłączonym autoload; 2 awarie syntetycznej MEMORY
  spowodowane wymuszonym MEMORY=off w wywołaniu testów. Nie zmieniano testów
  w celu ukrycia tych wyników. Poprawione wywołanie tych modułów:
  **32 passed**, 12.04 s (`tpa-2-broad-corrected-junit.xml`).
- Ostatnia szersza regresja z -p anyio.pytest_plugin, bez odziedziczonego
  JAZN_MEMORY_MODE/ROOT, bez live_model/live_mcp/private_data, --maxfail=10:
  **FAIL: 1 failed, 3539 passed, 31 skipped, 5 warnings**, 459.24 s,
  BROAD_FINAL_EXIT=1; zestaw doszedł do końca. Nie osiągnięto limitu 10 awarii.
  Awaria: `tests/test_mcp_http_cli_process_smoke.py::test_real_runpy_mcp_http_listener_and_catalog_are_responsive`
  (linia 118), probe zwrócił `mcp_catalog_invalid_http_framing`, metadata_verified=false
  i tool_catalog_verified=false. Nie wyłączono testu ani bramki. Nie ustalono,
  czy jest to błąd bazowego master w tym środowisku; nie deklarować tego bez
  porównania na izolowanym master z tym samym interpreterem i zależnościami.
  Kod transportu MCP nie był zmieniany w tej gałęzi; kontrakt wersji był.
  Log: `D:\.AI\codex_tasks\tpa-2-broad-final.log`;
  JUnit: `D:\.AI\codex_tasks\tpa-2-broad-final-junit.xml`.
  Ostrzeżenia: 4 historyczne deallocatory tkinter/Qt oraz celowy duplikat ZIP
  w teście tamper. Nie traktować ostrzeżeń jako oddzielnie zaliczonych kontroli.
- CI a9972b16 w ostatnim odczycie: 8 SUCCESS, 34 jeszcze bez końcowego wyniku,
  brak zakończonego FAIL. Końcowy HEAD raportu wymaga osobnego odczytu CI.
- **NOT RUN**: pełny plan na rzeczywistej Ollamie, fizyczne DPI/klawiatura,
  offline EXE i pełny odbiór operatora. Istniejące testy Qt nie zastępują ich.

Poniżej zachowano historię wcześniejszych etapów; jej wyniki dotyczą wskazanych
stanów, nie stanowią automatycznej walidacji późniejszego SHA.

- Etap III przed ostatnim utwardzeniem: **144 passed, 1 skipped**, 64.13 s.
- Etap III z kontrolą kompletnych dowodów live: **148 passed, 1 skipped**,
  61.20 s, jawny TPA_PYTEST_EXIT=0 i JUnit
  `D:\.AI\codex_tasks\tpa-2-stage3-proof-final-junit.xml`.
- Ostatnie zmiany (historia obserwacji, źródła ZIP/local, wersja): **36 passed**,
  9.60 s; Pyright całego tools/jazn_run_studio i nowych testów: **0 errors,
  0 warnings**. Rzeczywisty zweryfikowany lokalny eksport: **PASS**, raport
  `D:\.AI\codex_tasks\tpa-2-real-local-source-final.json`.
- Jeden pomocniczy przebieg Qt nie zwrócił podsumowania pytest (nie zaliczano
  go jako PASS). Końcowy przebieg jawnie tworzy QApplication przed testami
  mieszającymi QCoreApplication/QApplication i zapisuje kod zakończenia.
- Szersza regresja oraz końcowe CI .46 pozostają do wykonania po commit/push.

Interpreter testowy: `D:\.AI\codex_tasks\tpa-2-validation-venv\Scripts\python.exe`
(osobny venv z Python 3.14, system-site-packages, PySide6-Essentials 6.12.0).
Brak Qt w zastanych interpreterach; zainstalowano deklarowane opcjonalne Qt
wyłącznie do nowego venv. Nie instalowano nic do środowiska Jaźni.

- Pierwszy zestaw: **52 passed**, 33.84 s.
- Szerszy TPA przed poprawką layoutu: **113 passed, 2 failed, 1 skipped**.
  Dowiązanie Windows: ograniczenia procesu testowego. Retest z odpowiednimi
  uprawnieniami: PASS. Układ 860×580: poprawiono odstępy panelu, zachowując test.
- Retest układu i szerokości: **2 passed**, 1.41 s.
- Końcowy przebieg wszystkich TPA: **115 passed, 1 skipped**, 33.96 s.
  Komenda: wybrane przez `rg --files tests -g test_jazn_tpa*.py -g test_tpa_2*.py`
  aktywne testy (bez archive), `python -X utf8 -m pytest -q <pliki> --tb=short
  --basetemp=D:\.AI\codex_tasks\tpa-2-stage1-final-pytest
  --junitxml=D:\.AI\codex_tasks\tpa-2-stage1-final-junit.xml`.
- `py_compile` zmienionych modułów: PASS; `git diff --check`: PASS.
- Etap II, wszystkie aktywne TPA: **135 passed, 1 skipped**, 47.09 s.
  JUnit: `D:\.AI\codex_tasks\tpa-2-stage2-final-junit.xml`.
  Początkowo test hostile ZIP nie uwzględniał normalizacji ZipInfo na Windows;
  poprawiono fixture do oryginalnych bajtów nagłówka i odrzucanie orig_filename
  różnego od filename w produkcyjnym czytniku. Ostateczny test PASS.
- Po rozszerzeniu weryfikacji ZIP: **21 passed**, 12.67 s (sources i
  source_execution_qt), **0 błędów / ostrzeżeń Pyright**. Dodatkowe testy wersji
  i odmowy wykonania: **21 passed**, 5.09 s.
- Rzeczywisty master `55948d38` → kanoniczny staging → ZIP → resolver:
  **PASS**, release_verified=true, źródłowy SHA zachowany, manifest sprawdzony.
  Pierwsza próba wykryła nadmierne odrzucanie katalogu kodu latka_jazn/memory;
  rozdzielono go od prywatnego top-level memory i dodano regresję.
  Raport: `D:\.AI\codex_tasks\tpa-2-real-source-zip-result.json`.
- Kompilacja aktywnego drzewa z wykluczeniem tests/archive: **PASS**.
  Wcześniejsza próba bez wykluczenia wykazała dwa historyczne SyntaxError
  w niezmiennych snapshotach; archiwów nie modyfikowano.
- Pyright 1.1.414 dla wszystkich zmienionych modułów i nowych testów:
  **0 errors, 0 warnings**. Pełny check_types.py wykrył dodatkowo 2 zastane
  błędy Windows dla POSIX fcntl.ioctl/termios.TIOCSCTTY w niezmienionym
  pty_controlling_child.py; nie maskowano ich i nie zmieniano obcego modułu.
- Niezależne metadata --check dla `c1e177da`: **PASS**, synchronized=true,
  manifest_matches=true, provenance_matches=true (3554 pliki).
  Raport: `D:\.AI\codex_tasks\tpa-2-stage1-metadata-check.json`.
- Odczytano nieudane logi CI dla c1e177da: dwa nowe błędy typów naprawiono
  w etapie II; zastane POSIX typy Windows i niespójne wersje deployment/startup
  naprawiono w .45. Po poprawkach pełny Studio check_types.py: **0 errors,
  0 warnings**. Kontrakty runtime/PTY/wersji: **27 passed, 4 skipped**, 6.08 s.
  docs_truth_audit: **PASS**; sync_contract_catalog --check: **PASS**.
  CI końcowego SHA wymaga ponownego odczytu po pushu, wcześniejszy FAIL zachowano.
- Na etapie II pełne pytest, doctor, package-smoke i końcowe CI: NOT RUN / CI w toku
  dla wcześniejszego SHA. Nie stanowi to dowodu dla końcowego etapu II.
- Fizyczne Windows/DPI/EXE, rzeczywista Ollama i pełny odbiór operatorski:
  NOT RUN; testy Qt offscreen nie zastępują tych odbiorów.

## D. Pozostałe prace

1. Zweryfikować końcowy HEAD tego raportu i jego metadane oraz CI. P0–P2 są
   wdrożone z opisanymi granicami. Zdiagnozować FAIL framingu HTTP MCP:
   najpierw powtórzyć wskazany pojedynczy test na izolowanym master i tej gałęzi
   w tym samym venv; nie przypisywać go automatycznie zmianom TPA ani bazie.
2. Rzeczywisty pełny plan live z lokalną Ollamą: NOT RUN. Brak testowego modelu
   oznacza BLOCKED poszczególnych live, a nie PASS. Nie ruszać obcej Ollamy/daemona.
3. P3: kreator kolejnych półautomatycznych odbiorów,
   przyciski uruchom/odbiór/kontynuuj/checkpoint/historia. Zapis obserwacji
   ma nadal wymagać rzeczywistego wykonania i materiału z hashami.
4. Dalsze utwardzenie: wielkość historii
   i retencja (bez automatycznego usuwania), import znanych starszych schematów
   tylko na podstawie rzeczywistych fixture'ów, bez zgadywania formatu.
5. Etap V: szersza regresja z runbooka, idempotencja metadanych, Draft PR i
   potwierdzenie CI dla końcowego SHA. Nigdy merge bez osobnej zgody.

## E. Bezpieczeństwo i budżet

Główny `D:\.AI\jazn_latka_master` pozostał na master; kod edytowano wyłącznie
w osobnym worktree. Nie odczytywano prywatnych raportów/MEMORY ani baz.
Nie uruchamiano, nie zatrzymywano ani nie przejmowano produkcyjnego daemona.
Testy korzystają z fixture'ów i własnych procesów; nie wykonywano cleanup
cudzych zasobów. Pozostawiono testowy venv i raporty poza Git.
Nie wykonywano reset/rebase/force-push/merge. Wymagane uprawnienia Git i
testu dowiązań uzyskano przez mechanizm hosta, zgodnie z autoryzacją zadania.

Ostatni odczyt: 63% całej puli 300 minut, 64% tygodnia. Minimum 30% puli musi
pozostać niewykorzystane. Sprawdź aktualny licznik przed wznowieniem; historyczny
odczyt nie dowodzi stanu następnej sesji. Nie używano płatnych API ani agentów.

## F. Wznowienie

```powershell
Set-Location D:\.AI\jazn_branchs\tpa-2-auto-acceptance-history
git status --short --branch
git rev-parse HEAD
git ls-remote origin refs/heads/latka_work/tpa-2-auto-acceptance-history
git log -5 --oneline
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
```

Porównaj lokalne i zdalne SHA oraz PR/CI. Odczytaj AGENTS.md i AGENTS.codex.md,
ten checkpoint i plan. Przeczytano już pełne tpa_live.py, external.py,
release_staging.py i kontrakt izolacji. Następny krok: domknij walidację/push
etapu III, przeprowadź walidację i CI; następny etap funkcjonalny to kreator P3.
Przy tym budżecie nie zaczynaj go przed oceną rezerwy i zapisem checkpointu.
Powtarzaj tylko testy zależne od nowych zmian; końcowy gate musi dotyczyć
aktualnego HEAD. Ukończenie wymaga wszystkich warunków TPA 2.0 z planu,
rzeczywistych dowodów, branch/PR oraz jawnego rozdzielenia odbiorów manualnych.
Cały Goal pozostaje NIEUKOŃCZONY do spełnienia wszystkich wymagań.

## PROMPT_DO_KONTYNUACJI

Kontynuuj autonomicznie TPA 2.0 w SmuklyLew/jazn_latka, branch
latka_work/tpa-2-auto-acceptance-history, worktree
D:\.AI\jazn_branchs\tpa-2-auto-acceptance-history. Najpierw sprawdź licznik
wykorzystania 300-minutowej puli i tygodnia; nie przekraczaj 70% całej puli,
zostaw minimum 30%. Odczytaj AGENTS.md, AGENTS.codex.md, plan i checkpoint
docs/plans/TPA_2_0_*.md. Potwierdź HEAD, czystość, zdalny SHA, PR i CI.
Zachowaj wdrożone P0–P2: trwałą historię, zbiorczy stan 22 scenariuszy,
izolowane źródła master/SHA oraz trwałe plany zależności i timeouty.
Nie implementuj ich ponownie. Odczytaj końcowe CI i wyniki regresji.
Zapisana szersza regresja ma 3539 PASS, 31 SKIPPED i 1 FAIL:
test_mcp_http_cli_process_smoke.py::test_real_runpy_mcp_http_listener_and_catalog_are_responsive,
reason mcp_catalog_invalid_http_framing. Porównaj pojedynczy test na izolowanym
master i tej gałęzi przed diagnozą; nie osłabiaj testu ani fail-closed.
Następny etap funkcjonalny to brakujący półautomatyczny kreator P3, a potem
rzeczywiste odbiory i końcowe bramki release. Draft PR #443 już istnieje do master.
Używaj kanonicznego run.py → main.py i Controller/ChatClient; nie dodawaj
lifecycle ani finalizatora. Nierozstrzygniętą turę wznawiaj z tym samym
request_id. Nie dotykaj prywatnej MEMORY, aktywnych markerów i obcego daemona.
PASS regresji nie jest pełnym odbiorem. Nie zmieniaj starych testów bez
append-only archiwizacji. Po każdym etapie testy, checkpoint, commit, push
i potwierdzenie SHA. Gdy budżet niewystarczający, pozostaw zweryfikowany etap
z wypchniętym checkpointem i dokładną listą braków. Nie deklaruj ukończenia
całości bez rzeczywistych dowodów. Nie wykonuj merge.
