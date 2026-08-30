# Odbudowa pamięci Jaźni — Memory Rebuild v2.4

Kanonicznym programem operatorskim jest:

```powershell
py -X utf8 .\tools\memory_rebuild.py
```

## Finalny magazyn

W profilu v2.4 finalna pamięć jest przechowywana w jednej fizycznej bazie:

```text
memory_jazn.sqlite3
```

Jedna baza zawiera logiczne sekcje rozmów, dziennika, kandydatów, doświadczeń, pamięci L1/L2/L3, katalogu importów, konfliktów i ledgerów decyzji.

Historyczne pliki:

```text
archive_chats.sqlite3
journal.sqlite3
experience.sqlite3
import_catalog.sqlite3
```

pozostają obsługiwane jako baseline’y Testów 01–04 oraz źródła migracji. Nie są aktywnymi osobnymi magazynami finalnego systemu.

## Zgodność ze starszym narzędziem

Pierwotny pięciobazowy program został zachowany jako:

```text
tools/memory_rebuild_legacy_v24.py
```

Można go uruchomić przez główny launcher:

```powershell
py -X utf8 .\tools\memory_rebuild.py legacy --self-test
```

Flagi starego narzędzia są przekazywane do trybu zgodności. Domyślne uruchomienie bez takich flag otwiera nową aplikację v2.4.

## Obsługiwane źródła

- eksporty ChatGPT JSON i ZIP;
- ponumerowane części rozmów;
- HTML z osadzonym `jsonData`;
- kontrolny HTML `div.conversation` / `pre.message`;
- dzienniki JSON, JSONL i NDJSON;
- istniejące bazy SQLite Testów 01–04;
- pozostałe pliki jako źródła referencyjne bez automatycznego importu.

Import nowych eksportów jest przyrostowy i aktualizuje ten sam `memory_jazn.sqlite3`.

## Plan bez zapisu

Plan importu i migracji działa na tymczasowej kopii bazy. Docelowy plik nie jest zmieniany. Symulacja zachowuje kolejność źródeł i uwzględnia wynik każdego wcześniejszego importu.

## Kandydaci

Kandydaci są generowani z rozmów i dziennika jako materiał do ręcznego przeglądu. Aplikacja pozwala:

- zobaczyć kandydatów i dowody;
- edytować klasyfikację i treść z zachowaniem rewizji;
- dodawać dokładne fragmenty źródłowe;
- łączyć i rozdzielać kandydatów;
- zatwierdzać do doświadczenia L1;
- odrzucać albo przywracać do przeglądu.

Brak automatycznej promocji do L2 i L3 pozostaje twardą granicą.

## Testy

Profile `test01`, `test02`, `test03`, `test04` oraz `final` są bramkami jakości nad jednym aktualnym silnikiem. Finalny profil jest nadzbiorem wymagań historycznych testów i nie importuje tych samych źródeł cztery razy.

## Finalny eksport

Finalny eksport powstaje stagingowo, zawiera jeden `memory_jazn.sqlite3`, manifesty, ledgery, raport profilu finalnego, SHA-256 i pełną walidację SQLite. Publikacja nie aktywuje runtime.

Pełna instrukcja operatorska:

```text
docs/tools/REBUILD_MEMORY_APP.md
```
