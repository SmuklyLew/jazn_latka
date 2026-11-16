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
GET /ready służy tylko do potwierdzenia gotowości runtime. Monitor
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
