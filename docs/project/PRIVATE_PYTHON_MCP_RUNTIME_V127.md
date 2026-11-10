# V127 — prywatny interpreter Jaźni, JSS i lokalnego MCP

## Cel i zakres

Wybór ROOT/.venv jest wspólną domyślną trasą wykonywania procesów
`run.py -> main.py`, `run_studio.py` i potomnych poleceń operatorskich JSS.
Lokalne MCP dziedziczy wybór interpretera z JSS, chyba że operator jawnie
wskaże osobną ścieżkę `mcp_python`. Zdalny MCP/HTTPS to transport między
hostem ChatGPT a trwałym daemonem i **nie uruchamia** lokalnego interpretera
Pythona na maszynie klienta.

## Zasady V127

1. Jeśli `ROOT/.venv` nie istnieje, zachowaj kompatybilną trasę
   managed-environment/wheelhouse istniejącego Dependency Studio.
2. Jeśli `ROOT/.venv` istnieje, sprawdź `pyvenv.cfg`, ścieżkę programu,
   tożsamość `sys.prefix`, minimalną wersję Pythona i brak linków
   dla katalogu głównego. Nie przełączaj się po cichu na globalnego
   Pythona przy błędzie.
3. Podczas handoff na Windows użyj istniejącego
   `latka_jazn.dependencies.process_handoff`. Po handoff ponownie
   sprawdź wymagane zależności core, również jeśli ustawiono
   `JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE`. Sam plik `python.exe` nie
   jest dowodem gotowości pakietów.
4. `run_studio.py` pozostaje cienkim launcherem, nie staje się
   kolejnym control plane ani daemonem.
5. `mcp-http`, `run-studio` i inne extras nadal są profilami opcjonalnymi.
   Ich brak nie blokuje rozmowy przez gotowy rdzeń, ale lokalne MCP musi
   przejść kontrolę realnego wybranego interpretera.
6. Weryfikacja i wybór w `private_python_status` są tylko do odczytu:
   nie wykonują `pip install`, nie zakładają nowego `.venv`, nie
   zatrzymują daemona i nie dotykają pamięci.
7. Trwałe dane `MEMORY`, SQLite, dzienniki, checkpointy, heartbeat
   i aktywne markery pozostają poza odtwarzalnym `.venv`.
   Zdalny MCP musi mieć osobne auth/readiness, request identity,
   i accepted finalization; żaden lokalny PASS tego nie zastępuje.

## Kontrole odbioru

- Bez `.venv`: legacy startup bez regresji.
- Niekompletny `.venv`: odmowa uruchomienia, bez cichego fallbacku.
- Poprawny `.venv`: tożsamość sprawdzona przez krótki `-I -X utf8 -c`.
- Globalny interpreter z poprawnym `.venv`: preferowany handoff.
- Handoff do `.venv` bez wymaganych zależności: jawne zablokowanie aktywacji.
- Windows: uruchomienie GUI, Tk 8.6.15, obie kolejności testów,
  `pip check`, testy MCP, Test Studio i live TPA.
- Zdalne MCP: osobne end-to-end, autoryzacja, liveness, wersja,
  heartbeat i wznowienie tej samej tury bez replayu.
- Przed wydaniem: kanoniczna synchronizacja metadanych, katalogu
  testów oraz pełna wymagana macierz CI.

## Wskazówki dla operatora (PowerShell)

```powershell
$root = "D:\.AI\jazn_latka_v126_tpa"
$py = Join-Path $root ".venv\Scripts\python.exe"
& $py -X utf8 -c "import sys; print(sys.executable, sys.prefix, sys.base_prefix)"
& $py -X utf8 -m pip check
& $py -X utf8 -m pytest -q -ra --tb=short tests/test_private_python_selection.py
```

Nie nadpisuj istniejącego `.venv` w miejscu podczas naprawy.
Przed zmianą zależności korzystaj z zatwierdzonego, zweryfikowanego,
hash-locked offline wheelhouse i bezpiecznej procedury Dependency Studio.

## Źródła normatywne

- CPython 3.14 `venv`: https://docs.python.org/3.14/library/venv.html
- CPython `sys.prefix` i `pyvenv.cfg`: https://docs.python.org/3.14/library/sys_path_init.html
- PyPA `pyproject.toml`: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- pip Secure Installs: https://pip.pypa.io/en/stable/topics/secure-installs/
- MCP Python SDK v2: https://py.sdk.modelcontextprotocol.io/whats-new/
- MCP Client Transports: https://py.sdk.modelcontextprotocol.io/client/transports/
