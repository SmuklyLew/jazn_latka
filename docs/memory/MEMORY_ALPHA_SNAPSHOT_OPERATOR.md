# MEMORY alpha: bezpieczny snapshot operatorski (bez aktywacji)

## Zakres

Komenda `run.py memory-alpha-snapshot` jest elementem kanonicznego CLI.
Nie wywołuje `memory-recover`, `memory-converge`, `memory-attach`,
`start`, `stop` ani żadnego mechanizmu promocji L1/L2/L3.

- Bazy SQLite są kopiowane przez istniejące `create_sqlite_snapshot` /
  SQLite Online Backup API. Zatwierdzone transakcje WAL wchodzą do kopii DB.
- Zewnętrzne pliki `-wal`, `-shm`, `-journal` i
  `.runtime-write.lock` nie są kopiowane jako stan trwały.
  Niepusty rollback journal oznacza odmowę.
- Zwykłe pliki kopiowane są strumieniowo i sprawdzane SHA-256.
- **Przed utworzeniem stagingu** sprawdzamy źródłowe manifesty shardów:
  `size_bytes` każdego shardu musi odpowiadać rzeczywistemu fizycznemu
  plikowi źródłowemu. Niezgodność jest błędem, nie automatyczną naprawą.
- Po SQLite Backup API wolno skorygować rozmiar i istniejący, doradczy
  SHA-256 `active_write` **wyłącznie wewnątrz stagingu**, ponieważ WAL
  może zmienić wynikową bazę. Każda zmiana trafia do evidence, razem
  z poprzednią wartością. `sealed` wymaga zgodnego SHA-256 i rozmiaru.
  Nie ma automatycznej promocji.
- GitHubowe `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json`
  są osobnymi, **kanonicznymi metadanymi SYSTEM**, synchronizowanymi
  przez `release-hardening` po pushu, a nie przez ten snapshot MEMORY.
  Przy przejściu PR do Ready for review wymagana jest ich świeżość.
- Docelowy katalog nie może istnieć i nie może nakładać się na źródło.
  Dowiązania/reparse points są odrzucane.
- Zmiana rozmiaru lub mtime któregokolwiek z inwentaryzowanych plików
  (również sidecarów) podczas działania blokuje publikację.
- Wynik powstaje najpierw w `<destination>.incomplete-<uuid>`. Tylko po
  weryfikacji plików, wszystkich baz i manifestu evidence dochodzi do
  zmiany nazwy katalogu. W razie błędu staging pozostaje do diagnostyki.
- `ALPHA_SNAPSHOT_EVIDENCE.json` opisuje wszystkie objęte pliki,
  ich rozmiary, hashe i metody kopiowania. Oryginalny
  `MEMORY_PACKAGE_MANIFEST.json` jest zachowany jako dokument źródłowy,
  **nie** jest nowym manifestem transportowym v2/v3.

## Wymaganie krytyczne: quiescence

Przed komendą CREATE operator musi kanonicznie wstrzymać **wszystkie**
zapisy MEMORY (również Windows, WSL, usługi i kontenery). Nie zakładaj,
że sam brak procesu `python.exe`, otwartych uchwytów lub zmian w
krótkiej obserwacji oznacza brak writerów.

`--confirm-writers-paused WRITERS_PAUSED` jest tylko **atestacją**.
Komenda nie zatrzymuje daemona, nie zarządza supervisorami i nie dowodzi
quiescence. Jeżeli nie potrafisz zagwarantować utrzymania tego warunku
aż do zakończenia weryfikacji, nie uruchamiaj CREATE.

SQLite Backup API zapewnia spójny snapshot **pojedynczej** bazy.
Nie zapewnia atomowości całego zestawu SQLite + JSON/JSONL; w WAL
nie istnieje domyślna atomowość transakcji pomiędzy wieloma bazami.
Raport celowo ustawia `writer_quiescence_proven=false` i
`cross_database_atomicity_proven=false`.

## Przykładowe polecenia (Windows, katalogi przykładowe)

Operator potwierdza wstrzymanie writerów przed wykonaniem:

```powershell
python -X utf8 run.py memory-alpha-snapshot --mode create `
  --source "D:\\.AI\\jazn_latka_master\\memory" `
  --destination "D:\\.AI\\jazn_memory_alpha_snapshot_manual_01" `
  --confirm-writers-paused WRITERS_PAUSED --json
```

Kontrola niepublikująca (bez aktywacji):

```powershell
python -X utf8 run.py memory-alpha-snapshot --mode verify `
  --destination "D:\\.AI\\jazn_memory_alpha_snapshot_manual_01" --json
```

Postęp na terminalu jest podawany jako liczniki plików/bajtów i stron
SQLite. Przy `--json` komunikaty postępu idą do stderr, a raport na stdout.
Nie zgadujemy ETA dla transakcji SQLite ani nie wyświetlamy fikcyjnego
procentu całości podczas walidacji.

## Granica akceptacji

`ok=true` dowodzi sprawdzenia **konkretnego** katalogu migawki, nie
pełnego odzyskania Jaźni. Zawsze pozostają `false`:

- `writer_quiescence_proven`
- `cross_database_atomicity_proven`
- `application_restore_tested`
- `autobiographical_recall_tested`

Przed uruchomieniem Jaźni na odtworzonej pamięci wymagany jest osobny
izolowany test aplikacyjny ze skonfigurowanymi ścieżkami i bez praw zapisu
do produkcyjnej MEMORY. Nie podłączaj katalogu jako `active_root`.
Nie usuwaj wcześniejszych kopii OLD/NEW ani prywatnych źródeł.

Źródła SQLite:
- https://www.sqlite.org/backup.html
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/lang_attach.html
