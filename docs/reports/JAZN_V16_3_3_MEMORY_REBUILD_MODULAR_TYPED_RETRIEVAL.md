# Jaźń v16.3.3 — modularny Memory Rebuild i typowany retrieval

## Wynik implementacji

- Dodano kanoniczny, cienki launcher `tools/rebuild_memory.py`; poprzedni
  `tools/memory_rebuild.py` zachowuje zgodność.
- Oddzielono composition root, konfigurację, ustawienia i motyw UI.
- Wszystkie wymagane formaty przechodzą przez `PreparedSource` oraz
  `IntermediateRecord` do jednego wersjonowanego L0.
- HTML, ChatGPT JSON, dziennik, analizy utworów i legacy SQLite zachowują osobne
  adaptery.
- Jedna baza zawiera L0, zgodnościowe projekcje i oddzielną pamięć aktywną.
- Rewizje są dopisywane; poprzedni stan nie jest nadpisywany.
- FTS5 jest obowiązkowe, embeddingi są opcjonalne i domyślnie wyłączone.
- Dodano `TypedMemoryAPI` z filtrem temporalnym, proweniencją oraz wynikiem
  `UNKNOWN` przy braku wystarczającego dowodu.
- L2, L3, aktywacja i zastąpienie prywatnej pamięci pozostają fail-closed.

## Naprawione regresje

Walidacja FTS, wykrywanie gotowego schematu, inspekcja SQLite i kopiowanie
stagingowe używały miejscami zwykłego context managera `sqlite3.Connection`,
który zatwierdza transakcję, ale nie gwarantuje zamknięcia uchwytu. Na Windows
powodowało to `WinError 32` przy usuwaniu tymczasowych baz po dry-run. Połączenia
są teraz deterministycznie zamykane przez wspólny `ClosingSQLiteConnection`.

Pierwszy przebieg CI PR #161 ujawnił niepełny statyczny kontrakt hosta mixinów
oraz niejednoznaczne dla Pyrighta przekazanie `dict.get` jako klucza funkcji
`max`. Kontrakt deklaruje teraz inicjalizację, ustawienia, rejestr adapterów i
`ensure_initialized`, a wybór klasyfikacji źródła używa jawnej funkcji klucza.
Naprawa nie dodaje rzutowań, wyjątków analizatora ani osłabienia konfiguracji.

## Granica akceptacji

Testy syntetyczne i walidacje strukturalne nie są rzeczywistym benchmarkiem
prywatnego recall. Ta zmiana nie importuje prywatnych eksportów, nie zastępuje
aktywnej bazy i nie włącza L3 ani aktywacji.

## Walidacja

- pełny zestaw bez integracji live przed poprawką kontraktu typów:
  `1001 passed, 5 skipped`;
- obszar Memory Rebuild/Test04: `92 passed`;
- skupione regresje Memory Rebuild po naprawie typów: `30 passed`;
- szeroki lokalny przebieg po naprawie: `987 passed, 5 skipped`; pozostałe
  `14` testów zatrzymał wyłącznie błąd dziedziczenia uchwytu procesu
  `WinError 6/50` w lokalnym hoście Windows, poza zmienionymi modułami;
- kompilacja `latka_jazn`, testów i punktów wejścia: zaliczona;
- oba launchery uruchomione z obcego katalogu: zaliczone;
- `git diff --check`: zaliczone;
- chronione ścieżki, SQLite, eksporty prywatne i sekrety w zmianie: `0`.

Lokalne pobranie Pyright 1.1.411 zostało zablokowane przez błąd weryfikacji
łańcucha certyfikatu `UNABLE_TO_VERIFY_LEAF_SIGNATURE`; TLS nie został
osłabiony. Wiążący ponowny przebieg Pyrighta i pełnego zestawu wykonuje Ubuntu
w `release-hardening` PR #161.

Issue #59 pozostaje otwarte, ponieważ rzeczywisty benchmark prywatnego recall,
proweniencji i ciągłości po restarcie nie został wykonany.

Szczegóły architektury i komendy: `docs/tools/MEMORY_REBUILD_V16_ARCHITECTURE.md`.
