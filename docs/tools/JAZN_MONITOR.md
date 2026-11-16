# Jaźń Monitor (Windows/Ubuntu) — pasywny obserwator

Osobna aplikacja PySide6. Nie jest JSS, drugim runtime, hostem MCP ani supervisorem.
Nie wykonuje start/stop/restart, nie czyta prywatnej MEMORY, SQLite/WAL/SHM ani logów.
Zamknięcie okna **nie zatrzymuje** daemona ani Ollamy.

## Uruchomienie z checkoutu

    python -X utf8 jazn_monitor.py --root /sciezka/do/SYSTEM
    python -X utf8 jazn_monitor.py --root /sciezka/do/SYSTEM --probe-json
    python -X utf8 jazn_monitor.py --gui-smoke

Wybrany ROOT musi zawierać run.py oraz aktualny marker
workspace_runtime/JAZN_ACTIVE_RUNTIME.json. Wydzielone klony nie są
automatycznie traktowane jako aktywne. Monitor porównuje marker z
GET /live na 127.0.0.1:8787 (instancja, PID, aktywny root), a osobne
GET /ready służy do potwierdzenia readiness_ok i runtime_write_ready; zaakceptowana finalizacja jest osobną bramką. Monitor
nie udaje, że PID, zielona kropka czy odpowiedź HTTP oznacza zaakceptowaną
finalizację rozmowy. Wszystkie odczyty HTTP mają timeout i limit rozmiaru.
Brak dowodu → UNKNOWN, różnica właściciela instancji → ERROR.

Ollama GET /api/tags na 127.0.0.1:11434 dowodzi jedynie technicznej
dostępności API, nie wygenerowania odpowiedzi. MCP, JSS i supervisor
mają UNKNOWN bez oddzielnej, wiarygodnej weryfikacji. Dostęp do portów
poza localhost jest niedozwolony. Żadne żądanie nie wywołuje modelu.

## Pakowanie na Windows i Ubuntu

GitHub Actions (jazn-monitor-build.yml) wykonuje pytest, GUI offscreen,
PyInstaller onedir, smoke gotowego binarium i generuje SHA256SUMS.txt
wewnątrz katalogu dystrybucyjnego. Osobne artefakty Windows/Ubuntu.

PyInstaller nie jest cross-compilerem. Pakiet Linuksa wymaga zgodnego
glibc/Qt/sterowników; działanie na docelowym Ubuntu wymaga osobnego
manualnego odbioru. Te artefakty nie są podpisanymi instalatorami.
Przed publiczną dystrybucją zweryfikuj wymagania LGPL/GPL Qt/PySide6
oraz zachowaj odpowiednie noty/licencje.

## Ikona obszaru powiadomień (Windows / wybrane pulpity Ubuntu)

Na Windows Qt `QSystemTrayIcon` wyświetla ikonę monitora w obszarze
powiadomień. Standardowa minimalizacja lub przycisk `Do tray` ukrywają
okno, ale **nie kończą obserwatora** i nie wpływają na Jaźń. Ikona ma menu
`Pokaż Jaźń Monitor` oraz `Zakończ monitor`; kliknięcie/dwuklik
przywraca okno. Przycisk X kończy **tylko** proces monitora.

Na Ubuntu obsługa zależy od środowiska graficznego i dostępności
D-Bus StatusNotifierItem/XEmbed. Jeżeli `isSystemTrayAvailable()` jest
fałszywe, `Do tray` jest wyłączone, a minimalizacja pozostaje zwykłą
minimalizacją systemową (okno nigdy nie jest ukrywane bez możliwości
przywrócenia). Testy Qt mogą symulować obecność/brak tray w trybie
offscreen; rzeczywiste zachowanie wymaga odbioru w systemowej sesji GUI.

Źródło: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html
