# Jaźń Monitor v12722 — obserwowalność procesów i zadań

Stan: implementacja w [draft PR #483](https://github.com/SmuklyLew/jazn_latka/pull/483), baza: poprawka reconnect v12721. **Nie jest to automatycznie certyfikat realnego odbioru Windows.**

## Granice i zasada prawdy

- Monitor jest osobnym klientem GUI, **tylko do odczytu**. Nie zatrzymuje, nie restartuje ani nie przejmuje procesów i nie staje się drugim właścicielem runtime.
- `GOTOWY` dla daemon oznacza wyłącznie zgodność ROOT/PID/instancji, `/live` i świeży heartbeat; `/ready` oddzielnie potwierdza chat worker i runtime-write. Sama gotowość **nie potwierdza przyjętej tury**.
- `ZATRZYMANY` wolno stwierdzić wyłącznie przy dodatkowym źródłowym odcisku procesu i odczycie OS wskazującym brak PID. `NIEDOSTĘPNY` oznacza brak odpowiedzi przy częściowych danych. `NIEZWERYFIKOWANY` oznacza niewystarczające dowody; `BŁĄD` — wykazaną niespójność.
- Nowa zakładka „Procesy Jaźni” pokazuje tylko zweryfikowany daemon oraz jego potomków z wiarygodnym łańcuchem PID/czasu utworzenia. CPU oznacza **łączne sekundy CPU procesu**, a nie chwilowy procent obciążenia. RAM to `WorkingSet64` w MB.
- Zadania pochodzą z ograniczonych metadanych `daemon_chat_jobs.json` oraz liczników markera; nie są pełną historią wszystkich tur. Odrzucone zdarzenia mogą mieć kod z audytu SQLite odczytanego wyłącznie przez `mode=ro`; przy braku dowodu zostaje `—`. **Nie wyświetla się treści wiadomości, surowych argumentów procesów ani odpowiedzi modelu.**
- Zakładka „Finalizacja” pokazuje *ostatni widoczny status pracy* i odrzucenia. Status `completed_job` nie zastępuje pełnego envelope/accepted-finalization.
- Qt Monitor ma osobny `QLockFile` na wybrany ROOT, aby dwukrotne uruchomienie nie tworzyło dwóch okien. Zamykanie Monitora nie zatrzymuje daemona.

## Automatyczne uruchamianie

Po **zweryfikowanym interaktywnym** `run.py start` dispatcher `main.py` próbuje uruchomić osobny proces `jazn_monitor.py --root <ROOT> --daemon-port <port>`. Warunkiem są: zaufany root daemona, lokalny adres, dostępne PySide6, interaktywny terminal i interaktywna sesja pulpitu. To operacja typu *best effort*, która nie zmienia kodu wyjścia prawidłowo uruchomionego daemona.

Automatyczny start jest wyłączony w CI, `PYTEST_CURRENT_TEST`, `QT_QPA_PLATFORM=offscreen`, bez terminala TTY oraz bez obsługi GUI. Przy testach na żywym, interaktywnym Windows pozostaje włączony. Można go wyłączyć na poziomie **bieżącego procesu** ustawiając `JAZN_MONITOR_AUTOSTART=off`. Nic nie rejestruje się automatycznie jako usługa lub zadanie Harmonogramu.

## Kontrole operatorskie

```powershell
$python = "D:\.AI\.venv\Scripts\python.exe"
& $python -B -X utf8 .\jazn_monitor.py --root "D:\.AI\jazn_latka_v12721" --probe-json
& $python -B -X utf8 .\jazn_monitor.py --root "D:\.AI\jazn_latka_v12721"
```

Podczas odbioru sprawdzić Windows: (1) otwarcie Monitora po interaktywnym `run.py start`, (2) czy ponowny `start` nie tworzy duplikatu, (3) odczyt danych i poprawną tożsamość instancji, (4) odrzuconą turę z kodem bez treści użytkownika, (5) zamknięcie Monitora bez wyłączenia daemona, (6) brak GUI przy `package-smoke` i CI.

## Rzeczywisty odbiór Windows — 20 listopada 2026

- **PASS:** uruchomienie Monitora v12722 i czterech zakładek na Windows, obserwacja instancji v12721 i v12722 na odrębnych portach.
- **PASS:** poprawka `CREATE_NO_WINDOW` — operator potwierdził brak migających niebieskich okien PowerShell podczas odświeżania danych.
- **PASS (visible terminal):** lokalna sesja `local-v12722-reconnect-acceptance` / `8788` poprawnie odtworzyła `MALINA-628` po `/exit` i ponownym podłączeniu klienta.
- **PENDING:** odczyt odrębnych trzech `runtime_turn_completed` z rzeczywistej bazy audytu, potwierdzenie lineage i kanonicznej persistence; nie wykonano testu po restarcie daemona.
- **PENDING:** natywne nazwy plików procesu w Menedżerze zadań Windows — osobny branch i Draft PR po kontroli persistence.

Szczegółowe dowody, dokładny transkrypt i bezpieczna procedura audytu: [JAZN_V12722_WINDOWS_OLLAMA_RECONNECT_ACCEPTANCE_20261120.md](../reports/JAZN_V12722_WINDOWS_OLLAMA_RECONNECT_ACCEPTANCE_20261120.md).

## Ograniczenia obecnego zakresu

Ten patch nie zmienia `python.exe` na natywne `Jazn-Daemon.exe` w Menedżerze zadań Windows. Natywny plik EXE wymaga osobnego pakowania i odbioru rozdzielnego od obserwowalności; etykiety w aplikacji nie zmieniają nazwy obrazu procesu w systemie operacyjnym.

## Źródła zewnętrzne

- [Microsoft Win32_Process](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process): PID, ParentProcessId, CreationDate i niebezpieczeństwo ponownego użycia PID.
- [Microsoft Get-Process](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/get-process?view=powershell-5.1): czas CPU i pamięć.
- [Qt QLockFile](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QLockFile.html): bezpieczna wyłączność procesu i wykrywanie starych blokad.
- [Qt QThread](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html): probe poza wątkiem GUI.
- [Python subprocess](https://docs.python.org/3/library/subprocess.html): uruchamianie procesu i jego parametry na Windows.
