# v127.30.10 — etap 05: izolowany odbiór na PC (Windows)

Status: procedura przygotowana; rzeczywisty odbiór NOT_RUN. Nie jest instrukcją instalacji produkcyjnej. Przed testami potwierdzić wszystkie wymagane CI i readiness 16/16 exit_code=0 dla testowanego commita; jeśli metadata CI zmieni HEAD, potwierdzić wyłącznie katalog testów, manifest i provenance. Nie testować innego SHA pod nazwą tego samego wydania.

## 1. Klon i preflight

W nowym PowerShell, oddzielny katalog; nie modyfikować D:\.AI\jazn_latka_master, nie kopiować prywatnej MEMORY, .settings_local ani markerów. Sprawdzić czy nie ma konfiguracji środowiskowej wskazującej prywatne ścieżki pamięci/aktywnego runtime. W razie wątpliwości przerwać. Użyć istniejącego venv operatora, bez instalacji zależności. Przykładowy katalog musi być nieistniejący.

```powershell
$Branch = 'fix/v12730-10-pc-acceptance-remediation-20261126'
$Root = 'D:\.AI\jazn_latka_v12730-10_stage05_pc'
$Py = 'D:\.AI\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $Root) { throw 'Wybierz nowy katalog testowy' }
if (-not (Test-Path -LiteralPath $Py)) { throw 'Brak wskazanego interpretera' }
git clone --branch $Branch --single-branch https://github.com/SmuklyLew/jazn_latka.git $Root
if ($LASTEXITCODE -ne 0) { throw 'Klon nieudany' }
Set-Location -LiteralPath $Root
$ExpectedSha = Read-Host 'Pełny SHA kandydata zatwierdzonego do odbioru'
$ActualSha = (git rev-parse HEAD).Trim()
if ($ExpectedSha -notmatch '^[0-9a-f]{40}$' -or $ActualSha -ne $ExpectedSha) { throw 'SHA niezgodny z kandydatem odbioru' }
if (git status --porcelain) { throw 'Worktree nie jest czysty' }
$ActualSha
$env:JAZN_DEPENDENCY_AUTOBOOTSTRAP = '0'
$env:JAZN_MEMORY_MODE = 'off'
$env:JAZN_MEMORY_SYNC_MODE = 'off'
$env:JAZN_ALLOW_PAID_OPENAI = '0'
$env:JAZN_DAEMON_AUTOSTART = '0'
& $Py -X utf8 run.py --version
& $Py -m pip check
& $Py -X utf8 run.py host-preflight --json
```

Sprawdzić wynik preflight; nie omijać błędu, nie uruchamiać auto-recovery ani automatycznego pobierania. Jeżeli preflight nie przyjmuje --root, sprawdzić --help i użyć bieżącego katalogu. Zarejestrować SHA, interpreter, sys.prefix/base_prefix, wersję Ollama, logi wyników (bez sekretów). Najpierw celowane testy:

```powershell
& $Py -X utf8 -m pytest -q tests/test_stage05_*.py
```

PowerShell nie zawsze rozwija wildcard dla natywnych programów; jeśli pytest nie odnajdzie ścieżki, użyć:
```powershell
$Tests = @(Get-ChildItem tests -Filter 'test_stage05_*.py' -File | ForEach-Object { $_.FullName })
& $Py -X utf8 -m pytest -q @Tests
```

## 2. Izolacja Ollamy i daemonu

Wybrać wolne porty (przykładowo daemon 8796, Ollama 11435); sprawdzić Get-NetTCPConnection przed startem. Nie zatrzymywać istniejącej produkcyjnej instancji i nie uruchamiać testu w jej katalogu. Nie używać modelu cloud. W osobnym PowerShell uruchomić testową Ollamę:
```powershell
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_NO_CLOUD = '1'
ollama serve
```
Potwierdzić w logu "Ollama cloud disabled: true"; jeśli nie można uruchomić izolowanej instancji, test real Ollama BLOCKED, nie zatrzymywać produkcji. Nie pobierać modeli bez zgody. Na terminalu Jaźni:
```powershell
$Port = 8796
$env:JAZN_OLLAMA_BASE_URL = 'http://127.0.0.1:11435'
$env:JAZN_LLM_ROUTE = 'auto'
(Invoke-RestMethod "$($env:JAZN_OLLAMA_BASE_URL)/api/tags").models | Select-Object name
```
Wybrać faktycznie zainstalowany lokalny model; gemma3:latest tylko jeśli istnieje. Ustawić `$env:JAZN_OLLAMA_MODEL`. Odrzucić model cloud i brak logu local-only. Ustawić `$Model = $env:JAZN_OLLAMA_MODEL`. W każdym nowym PowerShell ponownie ustawić izolowany root, interpreter, port, wszystkie zmienne sekcji 1 i 2 oraz model; zmienne `$env:` nie są automatycznie przenoszone do niezależnego terminala. Przed każdym submit lub restartem sprawdzić, że `JAZN_OLLAMA_BASE_URL` jest dokładnie `http://127.0.0.1:11435` dla tego przykładu, model jest oczekiwany, port daemonu jest testowy, a root i SHA odpowiadają kandydatowi. Przy rozbieżności przerwać, bez fallbacku do portu produkcyjnego. Zweryfikować status nieaktywnego testowego daemonu i tożsamość root; potem wykonać odmowę rozmowy:
```powershell
& $Py -X utf8 run.py status --root $Root --daemon-port $Port --json
& $Py -X utf8 main.py --root $Root --daemon-port $Port --no-ensure-daemon --chat-gpt -- 'Test braku daemona'
& $Py -X utf8 run.py start --root $Root --daemon-port $Port
& $Py -X utf8 run.py status --root $Root --daemon-port $Port --json
```
Nie kontynuować jeśli status nie wskazuje tego samego root, wersji i instancji, live heartbeat oraz integralności/provenance. Zachować instance ID i PID. Start jest jawny operatora; nie automatyzować w zwykłym ChatGPT.

## 3. Macierz realnego odbioru

Wszystkie dane syntetyczne. Zapisuj surowe JSON, request/session/turn/trace, hash rekordu i finalizacji, znaczniki czasu, status przed/po. Odczyt nie jest nową turą. Nie re-submitować żądania po timeout; używać --daemon-result z tym samym ID. Przykład jawnego lokalnego submit:
```powershell
$Sid = 'stage05-pc-continuity'
$Rid = [guid]::NewGuid().ToString()
& $Py -X utf8 main.py --root $Root --daemon-port $Port --no-ensure-daemon --daemon-submit --daemon-channel ollama --ollama-model $Model --session-id $Sid --daemon-request-id $Rid -- 'Projekt nazywa się Mira.'
& $Py -X utf8 main.py --root $Root --daemon-port $Port --daemon-result $Rid
```
Jeżeli pending, odczytywać ten sam request; nie generować nowego ID na retry. W razie odmowy przed submit odnotować brak przyjęcia. Dla odrębnej nowej tury nowy ID i ten sam session_id. Testować tylko syntetyczne treści:
- przed awarią: zaakceptowana modelowa tura i zapis faktu; jeśli deterministyczna, odrębna tura wymagająca modelu. Zapisz dowód rzeczywistego wykonania LLM.
- niedostępność przed przyjęciem: zakończ wyłącznie izolowany `ollama serve` przez Ctrl+C; sprawdź daemon live z tym samym PID i instance. Jawna trasa Ollama odmawia bez submit; tryb auto bez modeli może dawać tylko autoryzowaną ograniczoną odpowiedź rdzenia. Sprawdź dowody, nie samą treść.
- awaria podczas generowania: ponownie uruchom izolowany Ollama, zleć nową, rzeczywiście modelową turę przez --daemon-submit, po potwierdzeniu pracy modelu zatrzymaj izolowaną Ollamę przed zakończeniem odpowiedzi. Poll dokładnie ten sam request. Jeśli odpowiedź skończyła się wcześniej, przypadek NOT_RUN, nie PASS. Sprawdź brak automatycznej ponownej wysyłki do innego modelu i brak niezaakceptowanej odpowiedzi; status daemona nadal live. Nie wywołuj sztucznego trzykrotnego replayu. Circuit breaker OPEN/HALF_OPEN wymaga obserwacji trzech odrębnych rzeczywistych awarii generowania i telemetrii, nie samej odmowy discovery.
- po awarii: ponownie uruchom Ollamę w tym samym izolowanym trybie, nowa tura z tym samym Sid: "Jak nazywa się projekt?" Sprawdź zaakceptowane źródło Mira, checkpoint/lineage, brak duplikatu, poprawną finalizację; niezależna sesja nie może przejąć faktu. Jeśli odczyt deterministyczny, odrębna tura modelowa potwierdza odzyskanie inferencji.
- restart testowego daemonu tylko po rozstrzygnięciu aktywnych jobów, przez run.py restart --root $Root --daemon-port $Port --json. Sprawdź nową instancję i prawidłowe odzyskanie tej samej sesji, brak replayu i niespójności.
- phase-2: kontrolowany lokalny MCP/JSONL/host-finalize na izolowanym daemonie, sprawdź odmowę po zmianie instancji/hasła kontraktu i bez live statusu; nie używaj prywatnych tokenów produkcji. Pełny live ChatGPT/MCP/Cloudflare należy do etapu 09.
- cleanup: rozstrzygnij joby, nie odtwarzaj niepewnego submit; zweryfikuj root/instance i brak supervisora dla testowego procesu; `& $Py -X utf8 run.py stop --root $Root --daemon-port $Port`, następnie status --json. Zatrzymaj wyłącznie izolowaną Ollamę, bez zmiany produkcji. Nie usuwaj zapisów testowych.

## 4. Kryterium odbioru

Każdy przypadek PASS/FAIL/BLOCKED/NOT_RUN wraz z SHA i dowodem. CI z symulacją nie zastępuje realnego odbioru modelu. Etap 05 nie jest zamknięty, dopóki pozostałe ryzyka autoryzacji i transportu nie są rozliczone oraz wymagane testy nie zostały zaliczone. Szczególnie: atomowość phase-2, ACK, pozostałe adaptery i zewnętrzne endpointy. Nie przechodzić do etapu 06 jako zakończonego 05 bez wyników. Źródło konfiguracji Ollamy: https://docs.ollama.com/faq .
