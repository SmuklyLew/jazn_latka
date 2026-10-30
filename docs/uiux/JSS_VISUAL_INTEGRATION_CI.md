# JSS Visual & Integration CI — projekt, izolacja i odbiór

## Cel

Workflow: .github/workflows/jss-visual-integration.yml. Uruchamia się na PR
do master dla zmian JSS; opcjonalnie po ręcznym workflow_dispatch z gałęzi
domyślnej. Nie scala, nie wdraża i nie tworzy produkcyjnego wydania.

| Job | Host | Sprawdzane funkcje | Artefakty |
| --- | --- | --- | --- |
| qt-visual | GitHub-hosted Ubuntu i Windows, Python 3.13 | PySide6, trzy style, 6 stron, minimalny viewport, nawigacja, layout, zapisywanie ustawień, obsługa błędu | PNG, report.json, report.md, index.html |
| windows-exe | GitHub-hosted Windows, Python 3.13 | istniejący build.py, hash EXE, manifest onedir, izolowany GUI smoke | pełny JaznRunStudio onedir, exe-report.json |
| gate | GitHub-hosted Ubuntu | wymagany sukces obu jobs | GitHub Job Summary |

Artefakty są przechowywane przez 7 dni. Upload na wypadek błędu zachowuje
dostępne diagnostyczne wyniki; brak artefaktu nie jest sukcesem.
Windows EXE to wyłącznie testowa kompilacja.

## Granice bezpieczeństwa

Visual runner tworzy NOWY katalog wynikowy poza checkout i odmawia nadpisania
istniejącego. W jego wnętrzu powstaje syntetyczny SYSTEM z trzema plikami
markerowymi, osobny katalog runtime, operator i lokalny HOME.
Żaden z markerów nie zawiera uruchamialnej implementacji runtime.

Przed importem Jaźni / Qt runner usuwa wszystkie odziedziczone wartości
środowiskowe o prefiksie JAZN_ i wymusza:
- JAZN_MEMORY_MODE=off;
- JAZN_MODEL_ADAPTER=null;
- JAZN_RUNTIME_WORKSPACE_DIR w katalogu wynikowym;
- JAZN_OPERATOR_STATE_ROOT w katalogu wynikowym;
- JAZN_MEMORY_ROOT w katalogu wynikowym;
- JAZN_ALLOW_NETWORK=0;
- QT_QPA_PLATFORM=offscreen.

Testowe okno używa Window(..., smoke=True); próby subprocess.Popen i
socket.create_connection są blokowane. Nie wolno wykonywać start/stop,
MCP, Ollama, tunelu ani odzyskiwania produkcyjnej MEMORY. Job EXE
dostaje niezależny syntetyczny SYSTEM oraz wyłączoną MEMORY. Runnery
są GitHub-hosted, nie self-hosted, nie otrzymują sekretów, mają tylko
GitHub permissions contents: read; checkout nie zachowuje credentials.

## Scenariusze i dowody

Dla każdej palety Technical Workbench, Operations Studio i Fluent Studio
jest potwierdzany zapis wyboru oraz render sześciu ekranów: Pulpit,
Usługi i procesy, Katalog testów, TPA, Ustawienia i Połączenie z ChatGPT.
Weryfikowana jest również mała wersja Usług (860×580).
Łącznie jest 7 PNG na profil, 21 obrazów; ostatni przedstawia
syntetyczną nieudaną operację: 22 PNG na platformę.

Pozostałe kontrole: Enter w wyszukiwarce, obecność i zmiana splitterów,
ukrywanie sidebara, zapis walidowanego layoutu, ochrona niezapisanej
zmiany portu MCP, prawidłowy stan błędu i brak fałszywej readiness,
brak uruchomionych zadań Controller.

Raport zapisuje wyłącznie nazwy testów, wyniki, względne nazwy PNG,
wymiary, rozmiary plików, SHA-256 i jawne oznaczenie syntetycznego
trybu. Nie eksportuje zmiennych środowiska, sekretów ani prywatnych logów.

Uwaga: obrazy są rzeczywistym renderingiem Qt, ale jeszcze nie
zatwierdzonymi obrazami referencyjnymi. Bramka nie wykonuje golden
pixel diff. W raporcie golden_baselines_verified=false; do pełnej
regresji pikselowej potrzebny jest odbiór wzorców dla OS/Qt/DPI.

## Odbiór w GitHub

1. PR #442 → Checks → JSS Visual & Integration CI.
2. Obie platformy Qt i Windows EXE muszą zakończyć się sukcesem.
3. Artefakty jss-visual-Windows-* oraz jss-visual-Linux-* zawierają
   index.html oraz obrazy. Sprawdź też report.json i report.md.
4. W exe-report.json zweryfikuj wynik, SHA-256, manifest i smoke exit=0.
5. Artefakt jss-Windows-test-EXE-* zawiera katalog onedir, nie sam EXE.
6. Po każdej zmianie gałęzi wymagaj świeżych dowodów z aktualnego HEAD.
7. Manualny odbiór prawdziwego Windows i realnego runtime pozostaje odrębny.

To CI nie potwierdza rozmowy z prawdziwym daemonem, Ollamy, ChatGPT,
OAuth, MCP ani continuity MEMORY. Takie testy pozostają poza zakresem
i nie mogą być symulowane jako zaliczone.

## Oficjalne źródła i kontrakty

- https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html
- https://github.com/actions/upload-artifact
- https://docs.github.com/en/actions/concepts/runners/github-hosted-runners
- https://pyinstaller.org/en/stable/
- AGENTS.md, AGENTS.codex.md, docs/uiux/JSS_SCREEN_CONTRACTS.md
- tools/jazn_run_studio/ACCEPTANCE.md


## CI .40 — poprawki po diagnozie PR #442

- Usunięto segment `../` z katalogu PNG: bezwzględna ścieżka na
  katalog sąsiadujący z checkout jest obsługiwana przez `upload-artifact`.
  Brak jakiegokolwiek raportu jest błędem uploadu, nie pozornym PASS.
- `VisualSystem` używa jednorazowego timera należącego do instancji Qt.
  Po **zaakceptowanym** zamknięciu `Window` zatrzymuje timer i usuwa
  filtr zdarzeń z globalnego `QApplication`, ograniczając ryzyko wywołań
  `reflow` po zniszczeniu widgetów. Dodano test cyklu życia GUI.
- `visual_ci.py` sprawdza typ `QScrollArea` przed dostępem do
  `horizontalScrollBar()`. Pełny Pyright pozostaje wymagany.
- Twardy próg 5 sekund dla zdrowia runtime nie został poluzowany.
  Problem wydajności Windows wymaga oddzielnego profilowania i
  potwierdzonej poprawy, nie omijania testu.

Zielony CI bieżącego HEAD jest wymagany przed uznaniem poprawki za
zweryfikowaną. Te zmiany nie ingerują w MEMORY ani produkcyjny daemon.
