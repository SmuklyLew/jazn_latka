# Jaźń — Serce Systemu

Jedna aplikacja operatorska rozwija istniejący Workbench Qt. `main.py` nadal zarządza komendami, runtime i finalizacją. CLI oraz rozmowa TTY korzystają ze zgodnego `run.py`. Wersja `.94.4` jest checkpointem rozwojowym; zakres niezakończonego odbioru opisuje raport etapu.

## Uruchomienie na Windows

W katalogu SYSTEM, w interpreterze ze zweryfikowanymi zależnościami profilu `core` + `run-studio`:

```powershell
python -X utf8 run_studio.py
python -X utf8 run_studio.py --check
python -X utf8 run_studio.py --version
python -X utf8 run_studio.py --gui-smoke
```

Środowisko użyte do lokalnego odbioru tego brancha:

```powershell
Set-Location 'D:\.AI\jazn_branches\jazn-v11603494-system-studio-diagnostics'
& 'D:\.AI\codex_tasks\jazn-run-studio-env\Scripts\python.exe' -X utf8 run_studio.py
```

Instalacja zależności pozostaje oddzielną operacją operatora w Studiu Zależności. GUI niczego automatycznie nie pobiera. `jazn_run_studio.py`, `tools/jazn_studio.py`, `main.py` i `run.py` pozostają dostępne. Dla testów i alternatywnych instalacji wskaż własny workspace przez `JAZN_RUNTIME_WORKSPACE_DIR`; nie kieruj testów do aktywnej MEMORY.

## Pierwsze uruchomienie

Splash pokazuje rzeczywisty etap budowy interfejsu. Kreator A/B/C sprawdza zadeklarowaną wersję Pythona, profile zależności, konfigurację i integralność w osobnym procesie. Nie pokazuje wymyślonych procentów. Niepowodzenie wymagania blokuje ukończenie kreatora, ale można anulować i otworzyć diagnostykę. Brak Ollamy, Git albo Cloudflare nie blokuje samego okna. Przyciski testów połączeń wykonują rzeczywiste odczyty endpointów.

Zakończenie wymaga zgody na zapis. Wynik kontroli jest powiązany z rootem, interpreterem i deklaracjami zależności. Po zmianie tego zakresu kontrola jest ponawiana. Menu **Konfiguracja → Kreator pierwszego uruchomienia** pozwala uruchomić go ponownie. Wybór modelu w Studio nie zmienia automatycznie adaptera działającego daemona; pełny profil ustawia Konfiguracja Qt.

## Przestrzeń pracy

Pulpit pokazuje wersję wybranego SYSTEM, niezależne wyniki integralności i pochodzenia, techniczny stan MEMORY oraz wybrany adapter/model. Pola aktualizuje publiczna komenda statusu. Brak kontroli pozostaje jawny. `null_model_adapter` nie oznacza działającego backendu, a dostępna konfiguracja Ollama nie oznacza sprawdzonej generacji. Status MEMORY nie potwierdza recall ani ciągłości autobiograficznej. Niepoprawna odpowiedź unieważnia wcześniejsze pozytywne wskazania. Poprawny negatywny status aktualizuje widok również po niezerowym kodzie komendy. Przycisk problemów otwiera istniejący panel, a ostatnia operacja wskazuje rzeczywiste zakończone zadanie.

- Domyślny motyw **Jaźń Violet Night**, zgodne wcześniejsze motywy i wybór własnego akcentu.
- Wyszukiwanie sekcji w górnym pasku. Enter otwiera pierwsze dopasowanie.
- Usługi: tabela statusu, PID, portu i gotowości; menu Akcje zawiera Start, Stop, Restart, Konfigurację, Logi i kontrolę szczegółów.
- Widok: panel operatora można dokować, odpinać, zamykać i otwierać; nawigację można przenieść na drugą stronę. Ctrl+B przełącza nawigację, Ctrl+J dotychczasowe logi.
- Ustawienia: kategorie, wyszukiwanie, walidacja, informacja o niezapisanych zmianach i przywracanie domyślnych wartości w formularzu. Zamknięcie ostrzega o niezapisanym formularzu. Parametry usług obowiązują przy ich kolejnym uruchomieniu.
- Problemy: bieżące nieudane operacje, grupowanie, czas, wyszukiwanie i przejście do modułu. Brak wykonanych kontroli jest odróżniony od braku problemów.
- Output/Logi: źródło, filtr tekstu, przewijanie oraz eksport po redakcji do nowego pliku.
- Terminal/Konsole: trzy niezależnie przewijane widoki rzeczywistych zadań. Nie są emulatorem PTY/ConPTY. Pełny TTY otwiera osobny terminal Windows po kliknięciu operatora.
- Developer: publiczne stany procesów, Git, diagnostyka, konfiguracja, katalog testów i raporty. Nie publikuje prywatnego rozumowania.

Układ zapisuje wyłącznie ograniczony, walidowany JSON z liczbami, wartościami logicznymi i zakresem kreatora. Nie deserializuje pickle ani dowolnego stanu obiektów Qt. Niepoprawny układ wraca do ustawień domyślnych. Lokalne ustawienia i raporty nie trafiają do Git.

## Runtime, modele i połączenia

Samo PID albo HTTP nie oznacza gotowości. Dla runtime kontrolowane są tożsamość procesu, endpoint, heartbeat i gotowość rozmowy. Żaden z tych paneli nie poświadcza zaakceptowanej widocznej tury. Rozmowa nadal przechodzi przez istniejący transport i kanoniczną finalizację.

Start/Stop/Restart Jaźni należą do `main.py`. Studio nie przejmuje obcych procesów Ollamy/MCP/tunelu. Start tunelu wymaga jawnego potwierdzenia. Zamknięcie Studio nie wysyła polecenia zatrzymania trwałego daemona. MCP, transport zdalny, uwierzytelnienie i gotowość hosta ChatGPT są oddzielnymi etapami diagnostyki.

Katalog testów pokazuje cele, kategorie i oczekiwania. Wykonanie testów i grup pozostaje dostępne w istniejących formularzach **Studia Jaźni → Testy** oraz w kompatybilnym Studiu Testów. Nie ukończono pełnej migracji wszystkich klasycznych edytorów do jednego natywnego formularza.

## Dla programisty

`tools/jazn_run_studio/app.py` współdzieli kontroler z trybami terminalowymi. `core.py` posiada rejestr zadań i istniejące adaptery komend. `requirements_worker.py` korzysta z kanonicznych usług deklaracji zależności i integralności. `first_run.py`, `operator_workspace.py` i `workspace_layout.py` należą do warstwy GUI, nie runtime. Zmiany nie dodają zależności Pythona.

Kontrola typów: `python tools/jazn_run_studio/check_types.py`. Regresje: istniejące `test_jazn_run_studio*.py` oraz nowe `test_heart_system*.py`. Pełna regresja i pakowanie są osobnymi bramkami. Historycznych testów nie edytowano.

## Źródła kontraktów interfejsu i transportu

Dokowanie opiera się na [Qt QMainWindow](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html), a blokowanie ukończenia kreatora na [Qt QWizard](https://doc.qt.io/qt-6/qwizard.html). Panel połączeń używa istniejących narzędzi zgodnych z [MCP 2026-07-28, transporty](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports); nie dodaje własnej implementacji protokołu.

## Konsola usług na wzór XAMPP (.94.6.19)

Na stronie **Usługi i procesy** zgromadzono sześć modułów: Runtime Jaźni,
Ollama, MCP lokalne, MCP publiczne (Cloudflare), Supervisor i MEMORY.
Wybór wiersza udostępnia pasek **Start / Stop / Restart / Status / Logi**.
Działania niedozwolone dla danego modułu są wyłączone; podgląd i konfiguracja
są dostępne w menu wiersza. PID, port i gotowość pochodzą wyłącznie
z kanonicznych odczytów, a nie z założenia, że istniejący PID oznacza zdrowie.

Start/Stop/Restart kieruje się do istniejących metod `Controller`: dla
Jaźni przez `run.py` i `main.py`, dla Ollamy oraz MCP wyłącznie w
odniesieniu do procesów uruchomionych i należących do tego Studio.
Supervisora sprawdza publiczne `run.py supervisor-status --json`; gotowość
wymaga potwierdzonej tożsamości, aktywności i aktualnego heartbeat.
MEMORY ma wyłącznie techniczny odczyt, bez dostępu do prywatnych baz.
Publiczny Cloudflare/MCP to diagnostyka, nie tryb uruchomienia
lokalnej bramy `--loopback-dev` jako niechronionego publicznego serwera.

Nie dodano bezwarunkowego **Start All / Stop All**. Trwały runtime,
supervisor i odrębne usługi wymagają jawnego planu, potwierdzenia właściciela,
kontroli zależności oraz kanonicznego zamykania i recovery. Wzorcem XAMPP jest
spójny panel, a nie kopiowanie procesu systemowych usług Apache.
Szczegółowe formularze OAuth, wdrożenia, mapy zależności i odbiór
funkcjonalny pozostałych studiów wymagają dalszych etapów. Nie są
potwierdzone przez samą obecność konsoli.

## Regresja odświeżania usług (.94.6.20)

Odczyt statusu supervisora w `refresh_services()` jest jawnie tylko do odczytu, tak jak kanoniczny status runtime i sondy sieciowe. Test Qt z poprzedniej wersji pomijał `action:supervisor`, dlatego został zaktualizowany bez usuwania funkcji. Historyczny test .19 zachowano bajt w bajt w `tests/archive/`. Pełny odbiór GUI i działania usług na rzeczywistym Windows nadal wymaga osobnej obserwacji operatora.
