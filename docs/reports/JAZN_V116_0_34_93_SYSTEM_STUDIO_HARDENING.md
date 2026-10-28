# Jaźń .93 — SYSTEM/Test Studio i Studio Startu

## Zmiany

- Przywrócono źródła wszystkich aktywnych kontraktów Test Studio w dystrybucji SYSTEM bez rozluźniania polityki wyłączania nazw prywatnych. Oryginalny test został zachowany byte-exact w `tests/archive/`.
- Dodano regresję sprawdzającą, że każda ścieżka w katalogu aktywnych testów istnieje i nie zostaje odrzucona przez filtr eksportu.
- Uszczelniono sanitację logów klasycznego Studio Startu: krótkie i cytowane wartości poświadczeń oraz userinfo w adresach HTTP. Zachowano jawne wartości logiczne dla zwykłych pól diagnostycznych.
- Wersja i katalog Studio Testów zsynchronizowane do 16.3.25.5.116.0.34.93.

## Dowód ograniczony do środowiska audytu

- W odizolowanej dystrybucji na Linux/Python 3.13: 33 celowane testy PASS oraz sprawdzenie `sync_contract_catalog.py --check` PASS.
- Nie jest to potwierdzenie działania produkcyjnego Windows/Ollama, prywatnego MEMORY, realnego połączenia ChatGPT ani zdalnego MCP/OAuth.
- CI wymagane na finalnym SHA gałęzi; release metadata wyłącznie przez kanoniczny `release_metadata_sync` / workflow.
- Nie wykonywano merge ani przepisywania historii Git.

## Pozostałe bramki

Pełny deterministic suite i Pyright w repozytorium, Windows Qt/operator P1–P5, rzeczywiste tury z Ollama, zewnętrzny MCP OAuth acceptance, historia niezamierzonych artefaktów build i weryfikacja antywirusowa EXE.
