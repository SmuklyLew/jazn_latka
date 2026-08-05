# Memory SQLite Test 04 — raport techniczny implementacji

## Punkt przywracania przed zmianami

- data preflightu: 2026-07-26;
- repozytorium: `SmuklyLew/jazn_latka`;
- branch: `feature/memory-sqlite-test-04`;
- commit: `621d76cea1bec68c4c2b890a0d4e12401e6fafb8`;
- `git status --short`: pusty;
- punkt przywracania: powyższy niezmienny commit przy czystym worktree;
- nie utworzono nowej gałęzi, taga, stasha ani kopii prywatnych danych.

Launcher `py` nie był dostępny w środowisku implementacyjnym. Te same komendy
preflight uruchomiono przez dostępny `python.exe` z `-X utf8`.

## Początkowa granica runtime

`run.py status --snapshot --json` zakończył się kodem `0`, ale nie potwierdził
żywego runtime: daemon był `inactive`, endpoint nie był sprawdzony w snapshot
read-only, marker był stary, a bieżąca wersja kodu różniła się od wersji
markera.

`run.py doctor --json` zakończył się kodem `0` i `ok=true` dla instalacji, ale
raportował osobno:

- `live_runtime_ready=false`;
- `activation_ready=false`;
- `release_metadata_current=false`;
- `transactional_memory_ready=false`;
- nieaktualny manifest paczki względem `latka_jazn/version.py`.

Nie potraktowano tych wyników jako dowodu aktywnej Jaźni ani gotowej pamięci.

## Zakres implementacji

Implementacja dodaje:

- cienki operator Windows PowerShell;
- moduł protokołu korzystający z istniejącego Memory Restore/Rebuild;
- wersjonowany manifest prywatnych źródeł;
- inwentaryzację i zamrożenie źródeł;
- plan-only, rebuild staging, idempotencję i drugi świeży rebuild;
- reconciliation Testu 03;
- pełną walidację pięciu SQLite;
- sanitizowany benchmark recall;
- format ręcznego testu wieloturowego;
- opcjonalny restart continuity;
- raport L2/L3 bez promocji;
- syntetyczne testy kontraktowe.

Nie zmieniono wersji i nie aplikowano historycznego patcha v24.0.1.

## Dane prywatne

Rzeczywiste eksporty ChatGPT nie były dostępne podczas implementacji. Nie
przeprowadzono prywatnego Memory SQLite Testu 04 i nie przedstawia się fixture’ów
syntetycznych jako dowodu przejścia na danych użytkownika.

## Walidacja i publikacja

Wyniki przed commitem implementacyjnym:

- `compileall`: kod `0`;
- parser Windows PowerShell 5 i `ScriptBlock.Create`: bez błędów;
- `tests/test_memory_sqlite_test04.py`: `17 passed`;
- pakiet Memory Rebuild, restore, private validation, recovery, wake-state,
  SQLite i Test04: `79 passed`;
- pełny zestaw bez markerów live: `384 passed`, `3 skipped`, `1 failed`;
- jedyna awaria pełnego zestawu jest stanem zastanym:
  `test_current_active_tree_has_no_old_package_version_references` oczekuje
  literalnie ówczesny cel migracji kończący się numerem `90`, zgodny wtedy z
  kanonicznym `version.py`; próba zmiany samego literalu ujawniła 268 istniejących
  historycznych odwołań, więc nie poszerzono tego zadania o migrację całego
  aktywnego drzewa;
- `run.py doctor --json`: kod `0`, `ok=true`, ale osobno
  `live_runtime_ready=false`, `release_metadata_current=false`,
  `transactional_memory_ready=false`;
- `run.py package-smoke --profile system --json`: kod `0`, `ok=true`,
  14 wymaganych kontroli przeszło, jedna opcjonalna kontrola historycznego
  manifestu źródłowego checkoutu nie przeszła; manifest izolowanego stagingu
  zweryfikował się poprawnie;
- `release_metadata_sync --write`: zgodnie z polityką odmówił na brudnym
  worktree; synchronizacja wymaga najpierw czystego commita implementacji;
- `git diff --check`: kod `0`;
- audyt ścieżek wyłączonych i wzorców sekretów: brak trafień.

Nie utworzono release’u. Commit, kanoniczna synchronizacja metadanych i push
muszą być raportowane na podstawie późniejszych, rzeczywistych wyników Git.

## Utwardzenie przed testami HTML

Przed lokalnym przebiegiem prywatnym dodano osobną fazę `HTML dry-run`, która
wywołuje istniejący `HtmlMemoryIngestor` wyłącznie w trybie bez zapisu. Źródła
HTML nie są przedstawiane jako równoważne kanonicznemu JSON i nie trafiają do
pięciu baz Memory Rebuild. Raport jest sanitizowany i potwierdza brak zmiany
docelowej bazy recovered-memory.

Dodatkowo ręczne zaliczenie testu wieloturowego wymaga autora i prawidłowego
timestampu ze strefą, a wykrywanie zduplikowanych członków ZIP działa liniowo.
Końcowy sukces developerski jest raportowany jako `developer_test04_passed`,
aby nie sugerować aktywacji pamięci ani decyzji L3.
