# JSS — architektura modułowego Workbench

JSS to **jeden proces aplikacji Qt**, ale nie jeden monolityczny widok. Publiczne wejście pozostaje `run_studio.py` → `tools/jazn_run_studio/app.py` → `window.py`. Studio jest **klientem** kanonicznego `Controller`, a nie alternatywnym runtime Jaźni.

## Powierzchnie interfejsu

- `window.py` — konstrukcja obudowy Qt, montaż widoków, kontrola potwierdzeń działań i bezpieczne zamknięcie.
- `workbench_shell.py` — menu, paleta poleceń, aktywność na lewej krawędzi i zakładki.
- `workbench_theme.py` / `visual_system.py` — tokeny wizualne, profile, kontrola dostępności i reflow.
- `operator_workspace.py` — jeden dokowany panel na dole lub z boku: problemy, logi, konsole, historia, terminal PTY.
- `workspace_layout.py` — ograniczony i walidowany stan układu, bez odczytu nieufnych bajtów Qt.

## Widoki funkcjonalne

| Moduł | Odpowiedzialność |
| --- | --- |
| `view_dashboard.py` | pulpit i gotowość systemu/modelu |
| `view_services.py` | statusy, odczyt dowodów, operacje usług i okno stanu |
| `view_chat.py` | czat lokalny, wybór modelu i wznowienie zaakceptowanej tury |
| `view_studios.py` | diagnostyka, TPA, katalog testów, MEMORY, inne Studia |
| `view_settings.py` | formularz profilu, motywy, CAS konfiguracji |
| `view_navigation.py` | nawigacja, przenoszenie paneli, zapis układu, narzędzia |
| `view_events.py` | zdarzenia asynchroniczne Controller → GUI, ACK finalizacji |

Moduły zawierają **zachowane metody** oryginalnego `Window`, skomponowane przez niewizualne mixiny. `Window` utrzymuje właścicielstwo instancji widgetów. Nie są tworzone dodatkowe procesy, serwery ani magazyny pamięci przez zmianę widoku.

## Zasady rozbudowy

1. Nowy ekran umieszczaj w odpowiednim `view_*.py`, a nie w `window.py`.
2. Nowe wywołanie procesu przeprowadź przez istniejący `Controller`, z weryfikacją własności i potwierdzeniem działań mutujących.
3. Warianty wyglądu modyfikuj przez tokeny `workbench_theme.py`, bez per-screen QSS i bez zewnętrznych URL.
4. Nowe elementy pracy operatorskiej kieruj do wspólnego `OperatorWorkspace`; unikaj konkurencyjnych terminali i duplikowania logów.
5. Zapewnij zachowanie fokusu, accessibility names, bezpieczeństwo odtwarzania układu i małego viewportu.
6. Potwierdzenie statusu to osobna czynność — kolor, PID, port lub nazwa modelu nie dowodzą gotowości runtime.
7. Po każdej zmianie uruchom testy Qt/Windows/Linux, Pyright, smoke z `--gui-smoke`, testy release i wygeneruj nowe screenshoty z `visual_ci.py`.

## Granice niezmieniane przez refaktor

- Żadnych zmian logiki `run.py` / `main.py` i niezależnej finalizacji rozmów.
- Zamknięcie JSS nie jest rozkazem `stop` dla daemona.
- Nie dotykaj `memory/`, `workspace_runtime/` ani prywatnych konfiguracji.
- Scalenie dopiero po pomyślnych checkach właściwego SHA; artefakty screenshotów są dowodem wyglądu, a nie aktywności Jaźni.
