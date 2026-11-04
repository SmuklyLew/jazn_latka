# Jaźń v88 — środowisko w ROOT i wyniki odbioru

Stan: instrukcja operatora i zapis wyników **przekazanych przez użytkownika** 2026-11-04. Nie jest to pełny odbiór wydania ani samodzielne wykonanie testów przez CI.

Testowany SHA: ddf958932cb1c250c63d65d2a755a077324614ea. Środowisko: Windows, Python 3.14.4.

## Lokalny Python w głównym folderze Jaźni

Docelowo: ROOT/.venv, bezpośrednio obok run.py, main.py, run_studio.py i pyproject.toml. Każdy linked worktree otrzymuje własne ROOT/.venv; nie współdzieli pakietów z master ani z innym worktree. Obecny .gitignore już ignoruje .venv/.

W tym folderze znajdują się interpreter, pyvenv.cfg, skrypty i biblioteki site-packages, **nie kod SYSTEM, MEMORY, modele Ollamy, markery daemonów ani sekrety**. Nie kopiuj istniejącego venv między katalogami — odtwórz go w docelowym ROOT. Nie umieszczaj .venv w Git, paczce SYSTEM i manifeście integralności.

Przykładowa jawna instalacja w wybranym worktree na Windows:

~~~powershell
Set-Location "D:\.AI\jazn_jss_modernization_20261103"
$root = (Get-Location).Path
if (Test-Path (Join-Path $root ".venv")) { throw "ROOT/.venv juz istnieje; nie nadpisujemy" }
py -3.14 -m venv (Join-Path $root ".venv")
if ($LASTEXITCODE -ne 0) { throw "Blad tworzenia venv" }
$projectPython = Join-Path $root ".venv\Scripts\python.exe"
& $projectPython -m pip install --only-binary=:all: -e ".[run-studio,mcp-http,test-evidence]" "httpx>=0.27,<1"
if ($LASTEXITCODE -ne 0) { throw "Blad instalacji profili" }
& $projectPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Niespojne zaleznosci" }
& $projectPython -c "import sys, mcp, pytest, PySide6; print(sys.executable)"
~~~

Instalacja wymaga jawnego uruchomienia i dostępu do pakietów; nie jest automatycznie wykonywana przez Jaźń. Offline/release pozostaje domeną Dependency Studio i hash-locked wheelhouse. Duże opcjonalne profile, np. polish-nlp, instaluj osobno. Nie usuwaj istniejących zewnętrznych venv bez niezależnego przeglądu.

JSS z wybranego ROOT uruchamiaj tak:

~~~powershell
& ".\.venv\Scripts\python.exe" -X utf8 run_studio.py --root "$((Get-Location).Path)" --isolated-acceptance
~~~

W JSS wybierz Python i (po pomyślnym preflight) Python MCP z ROOT/.venv/Scripts/python.exe. Zapisane wcześniej absolutne ścieżki do interpreterów są nadrzędne i nie mogą być nadpisane bez zgody operatora. W VS Code domyślnym wyborem projektu jest folder .venv; istniejący zapamiętany interpreter może wymagać ręcznego Python: Select Interpreter.

## Wyniki obserwowane na Windows dla SHA v88

| Obszar | Wynik | Granica dowodu |
|---|---|---|
| Dziewięć celowanych modułów | 95 PASS, exit 0 | Podzbiór testów |
| Test timeout i poll | 1 PASS | Jedno dopasowanie filtra; MCP wtedy niedostępne |
| Pełna regresja, długi basetemp | 3806 PASS, 3 FAIL, 27 SKIPPED | Trzy błędy TPA BLOCKED |
| Trzy TPA z krótką ścieżką | 3 PASS | Silna poszlaka limitu ścieżek, nie jednoznaczna przyczyna |
| Powtórzona pełna regresja | **3809 PASS, 0 FAIL, 27 SKIPPED, 6 WARNINGS; exit 0** | Krótka ścieżka tymczasowa |
| Izolowane MCP 2.2.0 | pip check PASS, import PASS | Osobny testowy venv |
| Moduły MCP/ChatGPT | **44 PASS, 0 FAIL, 0 SKIPPED** | Lokalna bramka, nie publiczna sesja ChatGPT |
| Ollama gemma3:latest | done=true, odpowiedź OK., 3 tokeny | Bezpośredni POST /api/chat |
| TPA ollama-two-turns | **PASS; 2 zaakceptowane finały, jedna sesja, osobny daemon zamknięty kanonicznie** | MEMORY=off; brak autobiograficznego recall |

Oryginalne XML/JUnit i logi TPA pozostały na dysku operatora; niniejsza tabela nie zastępuje ich niezmiennych artefaktów i niezależnej weryfikacji hashy.

## Domyślne gromadzenie dowodów przy przyszłych przebiegach

Używaj krótkiego, unikalnego --basetemp na Windows. Jawnie włączaj istniejący adapter tools.jazn_run_studio.test_evidence_plugin i przechowuj dowody w ignorowanym ROOT/.settings_local/jazn_studio/test-evidence. Nie zapisuj ich w MEMORY, workspace_runtime ani w .venv.

~~~powershell
$root = (Get-Location).Path
$py = Join-Path $root ".venv\Scripts\python.exe"
$base = Join-Path $env:TEMP ("jv88-" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Path $base | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:QT_QPA_PLATFORM = "offscreen"
$env:JAZN_TEST_EVIDENCE_DIR = Join-Path $root ".settings_local\jazn_studio\test-evidence"
& $py -X utf8 -m pytest tests -q -ra -p no:cacheprovider -p tools.jazn_run_studio.test_evidence_plugin --basetemp "$base\t" --junitxml "$base\results.xml"
Write-Host "Kod testow: $LASTEXITCODE"
Write-Host "JUnit: $base\results.xml"
git status --short
~~~

To **przykład**, a nie twierdzenie o jego wykonaniu. Nowy source SHA wymaga nowych dowodów. Przed release weryfikuj manifest, JUnit, pary TXT/JSON, niezmienne snapshoty i finalne CI zgodnie z docs/uiux/JSS_TEST_EVIDENCE_ARCHIVE.md.

Otwarte bramki: reconnect, resume bez replayu, restart daemona testowego, natywne GUI/DPI/ConPTY/EXE, publiczny MCP/OAuth ChatGPT, osobne MEMORY, finalne CI i kwalifikacja 27 pominiętych testów. **RELEASE_NOT_ACCEPTED**.

Źródła: https://docs.python.org/3/library/venv.html ; https://code.visualstudio.com/docs/python/settings-reference ; https://pip.pypa.io/en/stable/cli/pip_install/ .
