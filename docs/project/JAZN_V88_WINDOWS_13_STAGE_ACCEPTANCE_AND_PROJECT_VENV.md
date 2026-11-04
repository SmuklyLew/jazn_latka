# Jaźń JSS v88 — odbiór Windows i projektowe ROOT/.venv

Status: PATCH IN PROGRESS / RELEASE_NOT_ACCEPTED. Źródło: gałąź latka_work/jazn-jss-modernization-20261103, bazowy commit ddf958932cb1c250c63d65d2a755a077324614ea, 2026-11-04.

UWAGA: Wyniki poniżej pochodzą z logów przekazanych przez operatora Windows. Tego patcha nie testowano ponownie na tym komputerze; nowe zmiany kodu wymagają własnego zestawu testów i kontroli manifestu. Oryginalne XML i logi są lokalne, nie zostały załączone do repozytorium. Nie przypisuj im wyników nowszego HEAD.

## Docelowy wybór Pythona

Źródłowy Python 3.14.4 jest normalnie zainstalowany w Windows, a każdy checkout/worktree Jaźni używa własnego ROOT/.venv, obok run.py, main.py, run_studio.py i pyproject.toml. To NIE jest miejsce na prywatną konfigurację: .venv zawiera pyvenv.cfg, Scripts/python.exe lub bin/python i dystrybucje site-packages. Nie przenoś środowiska między katalogami, nie dodawaj go do Git, manifestu SYSTEM, ZIP, pamięci ani serwera.

Trwałe ustawienia: kanoniczne schematy i domyślne profile istnieją w repo, nadpisania operatora w .settings_local (lub już obsługiwanej kanonicznej lokalizacji), a MEMORY i workspace_runtime pozostają odrębnymi zasobami. Ten patch NIE przenosi istniejącej konfiguracji, nie usuwa katalogów i nie zmienia baz danych.

Kontroler JSS wybiera interpreter w kolejności:
1. jawny Settings.python (MCP: Settings.mcp_python lub Settings.python);
2. jawny JAZN_STUDIO_PYTHON;
3. ROOT/.venv/Scripts/python.exe (Windows) albo ROOT/.venv/bin/python (Linux);
4. uruchamiający interpreter hosta, dla zgodności ze starszymi instalacjami, jeżeli ROOT/.venv w ogóle nie istnieje i aplikacja nie jest EXE.

Jeśli ROOT/.venv istnieje, ale nie jest kompletnym środowiskiem, NIE wolno przechodzić po cichu na interpreter hosta. JSS prezentuje ścieżkę i błąd; uruchomienia procesów odmawiają wykonania. Wariant EXE bez żadnego interpretera wymaga jawnego wyboru.

Wybór jest odczytowy i dotyczy przyszłych procesów JSS, TPA, Test Catalog, MCP, komend run.py i workerów. Nie uruchamia daemona, nie pobiera pakietów, nie zmienia bieżącego procesu, nie ustawia sekretów i nie przejmuje obcych portów. Sprawdzenie wersji/dystrybucji MCP nadal następuje w osobnym preflight. Jeżeli operator wcześniej zapisał absolutną ścieżkę, pozostaje nadrzędna aż do jego zmiany.

## 13 etapów wykonanych lub zaplanowanych na PC

| Etap | Zakres | Dowód operatorski (Windows) | Status na bazowym SHA |
|---|---|---|---|
| 1 | Rozpoznanie master, 30 commitów względem gałęzi modernizacji, osobny detached worktree | master 5adef1d6; bazowy v88 ddf958932; czysty Git | PASS / przygotowanie |
| 2 | Wybrane testy Windows Supervisor, integralności, recovery, TPA/JSS | 95 passed, exit 0, Python 3.14.4 | PASS |
| 3 | Timeout -> poll -> jeden request bez replay | 1 passed; 13 modułów MCP pominiętych bez SDK; 3822 deselected | PASS tylko dla jednego testu |
| 4 | Pierwsza pełna regresja | 3806 passed, 3 failed, 27 skipped, 7 warnings; trzy TPA miały BLOCKED / git_sha=None | FAIL |
| 5 | Powtórzenie trzech TPA ze skróconym basetemp | 3 passed, exit 0, 10.67 s | PASS |
| 6 | Pełna regresja ze skróconym basetemp | **3809 passed, 0 failed, 27 skipped, 6 warnings, exit 0**, 561.05 s | PASS wykonanych testów |
| 7 | Analiza spójności starego .venv i dry-run MCP | pip check: charset-normalizer/jiter/numpy not supported; mcp==2.2.0 rozwiązywalne w dry-run | DIAGNOZA / częściowe |
| 8 | Oddzielny testowy MCP venv | mcp 2.2.0, pip check bez błędów, MCP_IMPORT_OK | PASS instalacji |
| 9 | 13 modułów MCP/ChatGPT, HTTP, OAuth i Tasks | **44 passed, 0 skipped, 0 errors**, 9.06 s | PASS kontraktów |
| 10 | Odczyt lokalnego API Ollama | /api/tags: qwen3.8:27b i gemma3:latest; /api/ps pusty | PASS dostępności API |
| 11 | Generacja na gemma3:latest | /api/chat, done=true, rola assistant, OK., eval_count=3 | PASS inferencji |
| 12 | TPA ollama-two-turns z izolowanym daemonem Jaźni | 2/2 accepted finals, jedna sesja, różne request/turn, PASS, canonical_stop, MEMORY=off | PASS tylko tej izolowanej ścieżki |
| 13 | Reconnect, resume tego samego requestu, daemon-restart, fizyczny odbiór Windows | W poprzedniej rozmowie zaplanowane jako kolejne scenariusze; brak końcowych logów z wykonania | **NOT_RUN / otwarte** |

Wnioski: skrócenie --basetemp skorelowało się z usunięciem trzech FAIL w pełnym przebiegu, ale dokładna przyczyna nie została rozstrzygnięta. 27 SKIPPED wymaga klasyfikacji (w tym opcjonalne MCP przed instalacją, PyNaCl, pyzipper, Windows ConPTY, POSIX-only oraz E2E wymagające host ZIP). Wynik 44 MCP pochodzi z osobnego venv i NIE oznacza zdalnego logowania ChatGPT/OAuth. Test TPA był przy MEMORY=off, więc nie udowadnia trwałego recall/autobiografii. Odbiór v88 z niezmienionego SHA NIE certyfikuje nowego patcha.

Dodatkowy etap lokalny po powyższych testach: operator utworzył ROOT/.venv z Pythonem 3.14.4 w testowym worktree, używając systemowego python.exe (sys._base_executable), z izolacją include-system-site-packages=false, profilem run-studio,mcp-http,test-evidence. pip check: bez problemów; import PySide6, mcp, pytest: ENV_READY. To odrębny dowód przygotowania środowiska, a nie ponowny odbiór runtime.

## Lokalna instalacja i obsługa

Istniejącego ROOT/.venv nie nadpisuj. Użyj oficjalnego venv tylko po świadomej decyzji operatora:

~~~powershell
Set-Location "D:\.AI\jazn_jss_modernization_20261103"
$root = (Get-Location).Path
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "ROOT/.venv missing or incomplete" }
& $py -m pip check
& $py -c "import sys, mcp, pytest, PySide6; print('ENV_READY'); print(sys.executable); print(sys._base_executable)"
git status --short
~~~

Pierwszą instalację wykonuj przez systemowego Python (np. py -3.14 -m venv .venv), a pakiety instaluj WYŁĄCZNIE wybranym .venv/Scripts/python.exe. Dodatkowe profile (archive, memory-cloud, polish-nlp) wymagają osobnej decyzji; nie są instalowane po cichu. Środowisko można odtworzyć z pyproject.toml i zweryfikowanego wheelhouse; nie należy go kopiować.

Uruchomienie JSS jawnie interpreterem ROOT:
~~~powershell
& ".\.venv\Scripts\python.exe" -X utf8 run_studio.py --isolated-acceptance
~~~

Gdy uruchomisz z zewnętrznego interpretera, nowy resolver wybierze ROOT/.venv dla kolejnych procesów, lecz sam proces GUI nadal używa tego Pythona, którym go uruchomiono. Preferowane jest uruchamianie całego JSS z ROOT/.venv.

## Przyszłe raporty i dowody

Przy testach Windows używaj krótkiego, unikalnego --basetemp; nie uruchamiaj pełnej regresji jednocześnie z operacjami na żywym daemonie/MEMORY. Zachowuj pełny JUnit, TXT/JSON i manifesty JSS w ignorowanym .settings_local/jazn_studio; nie w .venv ani MEMORY. Repo posiada już kanoniczny adapter tools.jazn_run_studio.test_evidence_plugin. Nie wytwarzaj w repo fikcyjnego XML/akceptacji za niezrealizowane testy.

Przykład (nowy przebieg, nowy HEAD musi otrzymać nowe dowody):
~~~powershell
$py = ".\.venv\Scripts\python.exe"
$base = Join-Path $env:TEMP ("jv88-" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Path $base | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:QT_QPA_PLATFORM = "offscreen"
& $py -X utf8 -m pytest tests/test_jss_root_venv_selection.py -q -ra -p no:cacheprovider --basetemp "$base\t" --junitxml "$base\results.xml"
Write-Host "pytest exit: $LASTEXITCODE"
~~~

## Kontrola końcowego SHA i kanoniczna synchronizacja wydania

Wersja patcha: 16.3.25.5.116.0.34.94.6.89-jss-project-venv-defaults. Jest nowym kodem względem 13 etapów wykonanych na bazowym v88. Te historyczne PASS nie zatwierdzają jego integralności.

Po sprawdzeniu nowego HEAD i przy czystym Git uruchom na Windows w testowym worktree (bez zmiany żywego daemona lub MEMORY):

~~~powershell
Set-Location "D:\.AI\jazn_jss_modernization_20261103"
$py = ".\.venv\Scripts\python.exe"
& $py -X utf8 -m pytest tests/test_jss_root_venv_selection.py tests/test_jazn_run_studio.py -q -ra
if ($LASTEXITCODE -ne 0) { throw "Targeted regression failed" }
git diff --check
& $py -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json
if ($LASTEXITCODE -ne 0) { throw "Release metadata synchronization failed" }
git status --short
~~~

To jest dopiero instrukcja wykonania na PC, **nie twierdzenie o wykonaniu**. Każdy zapis manifestu/provenance musi pochodzić z kanonicznego release_metadata_sync, a wynik powinien być sprawdzony pod kątem idempotencji, poprawnego SHA źródła i aktualnej wersji. Commit/push metadanych, pełna regresja Windows/Linux i finalny CI są osobnymi wymaganymi etapami. Nie edytuj manifestu ręcznie.

## Otwarta bramka RELEASE

Weryfikacja nowej gałęzi: py_compile/static checks, testy jednostkowe oraz TPA Windows dla nowego SHA; integralność PACKAGE_INTEGRITY_MANIFEST.json/SOURCE_PROVENANCE.json (kanoniczny mechanizm synchronizacji, nigdy ręczna fikcja hashy); ponowny MCP, Ollama i dwie tury. Następnie etap 13, fizyczny odbiór Windows GUI/SCM/ConPTY, brak naruszenia MEMORY i publiczny MCP/OAuth na rzeczywistym hoście. Dopóki tego brak, pozostaje RELEASE_NOT_ACCEPTED.

Źródła: https://docs.python.org/3/library/venv.html ; https://code.visualstudio.com/docs/python/environments ; https://docs.pytest.org/en/stable/how-to/output.html ; docs/uiux/JSS_TEST_EVIDENCE_ARCHIVE.md .
