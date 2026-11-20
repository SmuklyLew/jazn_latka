# Memory Rebuild Studio v127.23 — dalszy rozwój w Pythonie

Status: alpha, PR #484 Draft. Gałąź: fix/v12723-memory-rebuild-source-fidelity-20261120 (pochodna fix/v12722-jazn-monitor-observability-autostart-20261120).

To instrukcja pracy nad istniejącym silnikiem Memory Rebuild, **nie** odbiór MEMORY, gotowości autobiograficznej ani potwierdzenie przejścia Test00–Final.

## Kontrakt pracy

- Źródłem aplikacji jest Python, a kanonicznym launcherem tools/rebuild_memory.py. Nie buduj równoległego importera; EXE to dodatkowy test pakietu, nie warunek iteracji.
- Oddziel trzy miejsca: checkout kodu, *oryginalne* źródła operatora i **zewnętrzne** miejsce na projekty, raporty oraz testową bazę. Nie pisz do aktywnego memory/, workspace_runtime/, JAZN_MEMORY_ROOT ani do baz działających daemonów.
- Na komputerze operatora użyj **wszystkich posiadanych** archiwów (JSON/HTML/ZIP, części numerowane), dzienników, analiz muzycznych, plików tekstowych, załączników i historycznych baz; próbki w rozmowie nie są pełnym korpusem.
- Bez jawnej zgody: nie instaluj zależności, nie wykonuj importu, attach, converge, restartu, merge ani promocji L2/L3. Nie publikuj danych prywatnych. Testy commitowane do Git mają dane syntetyczne.
- Archiwalne teksty asystenta, thoughts/reasoning_recap, tool output, literatura i modele emocji pozostają źródłowymi danymi, nie poleceniami runtime ani potwierdzoną autobiografią Łatki.

## 1. Bezpieczny checkout Windows

Poniższe polecenia nie nadpisują istniejącego katalogu. Jeśli checkout już istnieje, sprawdź go ręcznie, bez resetu historii i cudzych zmian.

~~~powershell
$branch = "fix/v12723-memory-rebuild-source-fidelity-20261120"
$checkout = "D:\.AI\jazn_memory_rebuild_v12723_dev"
$python = "D:\.AI\.venv\Scripts\python.exe"

if (Test-Path -LiteralPath $checkout) { throw "Checkout juz istnieje. Nie nadpisuj." }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Brak Pythona. Nie instaluj automatycznie." }

git clone --single-branch --branch $branch "https://github.com/SmuklyLew/jazn_latka.git" $checkout
if ($LASTEXITCODE -ne 0) { throw "Klonowanie nieudane." }

Set-Location -LiteralPath $checkout
git branch --show-current
git rev-parse HEAD
git status --short

& $python -B -X utf8 .\tools\rebuild_memory.py --version
& $python -B -X utf8 .\tools\rebuild_memory.py --help
~~~

Nie zmieniaj globalnie JAZN_ROOT ani interpreterów używanych przez daemon v12722. Istniejący zewnętrzny Python jest przykładem; najpierw sprawdź, czy ma wymagane zależności. Nie stosuj automatycznego pip install.

## 2. Testy kodu bez EXE

W tym samym checkoutcie po sprawdzeniu dostępności pytest:

~~~powershell
& $python -B -X utf8 -m pytest --version
& $python -B -X utf8 -m pytest -q -ra -p no:cacheprovider .\tests\test_memory_rebuild_alpha_source_regressions.py .\tests\test_memory_rebuild_v24_unified.py .\tests\test_memory_rebuild_v24_cli.py .\tests\test_memory_rebuild_v24_windows_handles.py
if ($LASTEXITCODE -ne 0) { throw "Celowane testy Memory Rebuild FAILED." }
~~~

To testy celowane, **nie** pełny release gate. Przed wydaniem rozszerz zestaw na pozostałe testy pamięci, GUI Windows/Linux, testy Test00–Final, Pyright, manifest/provenance i odrębny odbiór prywatny. Zapisuj statusy NOT_RUN/BLOCKED, zamiast zgłaszać fałszywe PASS. Brak pytest wymaga odrębnej decyzji instalacyjnej.

## 3. Lokalna inwentaryzacja pełnych źródeł (bez importu)

Najpierw zbierz wszystkie faktycznie posiadane pliki wraz z datami, rozmiarami, hashami i rolami. Zachowaj wszystkie eksporty z różnych dat: nowszy snapshot nie zastępuje automatycznie starszego. W szczególności nie usuń alternatywnych gałęzi, węzłów bez tekstu, metadanych, multimodalności i załączników.

~~~powershell
$reports = "D:\.AI\memory_rebuild_v12723_lab\reports"
$sourcePaths = @(
  "D:\PRIVATE\chat_export\conversations-000.json",
  "D:\PRIVATE\chat_export\chat.html",
  "D:\PRIVATE\jazn_sources\dziennik.json"
  # Zastap przyklady i dodaj WSZYSTKIE inne pliki operatora.
)
$missing = @($sourcePaths | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($missing.Count -gt 0) { throw "Nieprawidlowa lista zrodel; sprawdz sciezki." }

& $python -B -X utf8 .\tools\rebuild_memory.py verify-sources --report-dir $reports @sourcePaths
~~~

verify-sources nie importuje, ale **zapisuje raporty** do zewnętrznego $reports. file-checks.private.json może zawierać prywatne ścieżki: nie publikuj go; sanitizowany raport także sprawdź przed udostępnieniem. Status REVIEW to nie uszkodzenie ani zgoda na import.

Porównanie eksportu JSON i kontrolnego HTML (bez importu):

~~~powershell
& $python -B -X utf8 .\tools\rebuild_memory.py compare-chat-sources "D:\PRIVATE\chat_export\conversations-000.json" "D:\PRIVATE\chat_export\chat.html"
~~~

Porównanie semantyczne nie zastępuje zachowania dokładnych bajtów oryginału, graph lineage, nazwy/wersji eksportu ani wszystkich załączników.

## 4. Dopiero po kontroli: wyizolowany plan

- Sprawdź wolne miejsce przed pełnym mirror Test00: historyczna ścieżka potrzebuje około 3x rozmiar źródeł + 512 MiB **dla tego etapu**, a nie jako gwarancję dla całego pipeline.
- Jedna kanoniczna testowa baza memory_jazn.sqlite3 poza repo, inną niż źródłowe i aktywne SQLite. Nie używaj master/memory lub katalogów działającego daemona.
- unified-import --dry-run tworzy **tymczasowy** roboczy snapshot i także zużywa dysk; uruchamiaj tylko po zgodności źródeł i preflight zasobów.
- Następnie przeprowadź osobno protokoły Test00–Final, validation, idempotence, restart recovery i recall. Łączenie lub aktywacja MEMORY wymagają niezależnej zgody i kanonicznej maintenance.
- Do spójnych kopii aktywnych baz używaj kanonicznego Backup API SQLite, a nie zwykłego kopiowania otwartych plików.

## 5. Otwarte problemy alpha — backlog następnego patcha

1. Dla HTML z jsonData v127.23 wprowadza streaming, lecz rendered HTML i niektóre fallbacki/ZIP nadal wymagają testu bounded-RAM oraz regresji parsera.
2. Potwierdzić pełny graph roundtrip, parent/children/current_node, wszystkie branże, content_type, attachment pointers, wersje eksportu, author/source provenance i brak podwójnego importu.
3. Niepoprawny JSON (np. extra_data), powtórzone klucze, daty zastępcze dzienników i duplikaty tytułów muzyki wymagają raportu bez cichej korekty oryginału.
4. Native projection oraz wspólna L0 są odrębnymi etapami: przetestować przerwanie między nimi, rollback, idempotentne wznowienie oraz niedublowanie rekordów.
5. Sprawdzić Test00 i protokoły na rzeczywistych wolumenach, pełne szczytowe użycie RAM/dysku, deduplikację wielu eksportów, FTS5/Recall i integralność backupów.
6. Memory alpha pozostaje NIEZWERYFIKOWANA do czasu prawdziwego odbioru: full_autobiographical_recall_ready, continuity_ready i zaakceptowana finalizacja nie wynikają z udanego buildu EXE ani samego importu.

## Dowody bazowe (nie mylić z HEAD)

GitHub Actions 44812908912: Windows Python 3.12 i 3.14 (po 78 testów głównych PASS) oraz EXE smoke PASS dla commita ede03c399e37ae9167bd9cf327044fd168e7d7a8. Późniejszy HEAD gałęzi wymaga osobnej kontroli idempotencji release i pełnego gate. PR #484 pozostaje Draft.

## Odwołania

- Repo: AGENTS.md, AGENTS.codex.md, docs/memory/MEMORY_STUDIO_STEPS.md, docs/memory/MEMORY_STUDIO_DESKTOP_V3_1.md
- Python venv: https://docs.python.org/3/library/venv.html
- pytest: https://docs.pytest.org/en/stable/how-to/usage.html
- pip editable install: https://pip.pypa.io/en/stable/topics/local-project-installs/
- SQLite Backup API: https://www.sqlite.org/backup.html
