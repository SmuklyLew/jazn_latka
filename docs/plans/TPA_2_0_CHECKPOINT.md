# TPA 2.0 — checkpoint

## A. Tożsamość

- Repozytorium: SmuklyLew/jazn_latka.
- Branch: `latka_work/tpa-2-auto-acceptance-history`.
- Worktree: `D:\.AI\jazn_branchs\tpa-2-auto-acceptance-history`.
- Baza: `origin/master`, `55948d3813664923ae64c6e24f345369632a1b24` (fetch wykonany).
- HEAD: commit zawierający ten checkpoint; odczytaj `git rev-parse HEAD`.
  Nie wpisujemy samoodnoszącego się SHA do zawartości commita.
- Wersja: `16.3.25.5.116.0.34.94.6.45-tpa-source-integration`.
- Data: 2026-10-30 (Europe/Warsaw).

## B. Prace i mapa modułów

Checkpoint etapu I został wypchnięty i zweryfikowany na GitHub:
`d79c2473839f76d88a59e6f2af5c9728a817ee70` (kod),
`c1e177da4aad741c413b00e6820743efd64af33d` (metadane).
Draft PR: https://github.com/SmuklyLew/jazn_latka/pull/443 (base master).
Etap II wypchnięty jako `13bd41bd` (kod) / `0cfd879bc8d67a4f66d6ab1a79eb650bbeacda6f`
(metadane); potwierdzono zgodność lokalnego i zdalnego SHA.

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
- Pełne pytest, doctor, package-smoke i końcowe CI: jeszcze NOT RUN / CI w toku
  dla wcześniejszego SHA. Nie stanowi to dowodu dla końcowego etapu II.
- Fizyczne Windows/DPI/EXE, rzeczywista Ollama i pełny odbiór operatorski:
  NOT RUN; testy Qt offscreen nie zastępują tych odbiorów.

## D. Pozostałe prace

1. P1: resolver, wykonanie w detached kopii i rzeczywista weryfikacja ZIP
   są zaimplementowane i sprawdzone; domknąć metadane/push poprawek CI .45.
2. P2: zależności preflight → regresja → daemon → dwie zaakceptowane tury →
   reconnect → resume tego samego nierozstrzygniętego request_id → własny restart.
   Oddzielne timeouty faz i jawne BLOCKED dla zależnych kroków.
3. P3: kreator kolejnych półautomatycznych odbiorów, trwały plan/resume,
   przyciski uruchom/odbiór/kontynuuj/checkpoint/historia. Zapis obserwacji
   ma nadal wymagać rzeczywistego wykonania i materiału z hashami.
4. Dalsze utwardzenie: kontrola aktualnego źródła w chwili zapisu obserwacji,
   ponowna walidacja 12 odbiorów zależnych studios-parity, wielkość historii
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

Ostatni odczyt: 32% całej puli 300 minut, 59% tygodnia. Minimum 30% puli musi
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
etapu II i przejdź do planu zależności P2; nie przebudowuj kanonicznego lifecycle.
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
Zachowaj wdrożoną trwałą historię i zbiorczy stan 22 scenariuszy. Implementuj
następne etapy w kolejności P1 izolowane źródło master/SHA, P2 plan zależności
i timeouty, P3 półautomatyczny kreator, następnie regresje i Draft PR do master.
Używaj kanonicznego run.py → main.py i Controller/ChatClient; nie dodawaj
lifecycle ani finalizatora. Nierozstrzygniętą turę wznawiaj z tym samym
request_id. Nie dotykaj prywatnej MEMORY, aktywnych markerów i obcego daemona.
PASS regresji nie jest pełnym odbiorem. Nie zmieniaj starych testów bez
append-only archiwizacji. Po każdym etapie testy, checkpoint, commit, push
i potwierdzenie SHA. Gdy budżet niewystarczający, pozostaw zweryfikowany etap
z wypchniętym checkpointem i dokładną listą braków. Nie deklaruj ukończenia
całości bez rzeczywistych dowodów. Nie wykonuj merge.
