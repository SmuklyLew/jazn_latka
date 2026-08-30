# Jaźń Memory Rebuild — Stage4

Ta wersja jest zgodnościowym następcą `tools/memory_rebuild.py` v2.4.

## Co zachowuje

- domyślne uruchomienie aplikacji Memory Rebuild v2.4;
- projekty, Studio i wszystkie istniejące `unified-*`;
- tryb `legacy` i kompatybilność ze starym `memory_rebuild_legacy_v24.py`.

## Co dodaje

Nowa rodzina poleceń:

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 ...
```

Stage4 jest przeznaczony do etapu Testu 04 i finalnej odbudowy **jednej fizycznej bazy**:

```text
memory_jazn.sqlite3
```

### Obsługiwane źródła

1. pełne rozmowy ChatGPT:
   - HTML,
   - JSON,
   - ZIP eksportu ChatGPT;
2. dziennik:
   - JSON,
   - JSONL/NDJSON;
3. `analizy_utworow.json`;
4. jawnie wskazane stare bazy SQLite Test01–04/legacy;
5. bieżące runtime L0:
   - `memory/raw/dziennik.json`,
   - `memory/layered/*.jsonl`.

## Model bezpieczeństwa

- źródła są tylko odczytywane;
- `plan` pracuje na bazie tymczasowej i nie zmienia celu;
- `build` pracuje na stagingowej SQLite;
- istniejąca baza jest snapshotowana przez SQLite Backup API;
- publikacja następuje dopiero po walidacji;
- finalne zastąpienie pliku używa `os.replace()`;
- wykonywane są `PRAGMA integrity_check`/`quick_check` oraz `PRAGMA foreign_key_check`;
- brak automatycznej promocji L2/L3;
- kandydaci mogą być generowani, ale pozostają `pending_review`.

## Rozszerzenie Stage4 w tej samej SQLite

Skrypt nie tworzy drugiej bazy. Do `memory_jazn.sqlite3` dodaje logiczne tabele:

```text
stage4_meta
stage4_sources
music_analyses
affective_observations
stage4_runs
```

### `music_analyses`

Zachowuje strukturę analiz utworów bez spłaszczania:

- tytuł,
- emocje,
- gatunek,
- tematyka,
- związek z książką,
- analiza,
- lustro emocji,
- refleksja,
- własne odczucia,
- introspekcja,
- podsumowanie,
- pełny `raw_json`,
- SHA-256 i proweniencja.

Każda analiza jest również projektowana do istniejącego dziennika L0, dzięki czemu korzysta z istniejącego wyszukiwania i późniejszego ręcznego procesu kandydatów.

### `affective_observations`

Zachowuje źródłowo oznaczone:

- emocje,
- uczucia,
- wrażenia,
- refleksję,
- kontekst,
- czas,
- źródło,
- SHA-256 źródła,
- `truth_status`,
- confidence/importance,
- granicę prawdy.

To są **operacyjne/modelowane rekordy afektywne**. Ich istnienie nie jest dowodem biologicznego odczuwania ani ciągłego przeżywania w tle.

## 1. Plan bez zapisu

Przykład:

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 plan `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --source-dir "D:\.AI\work\memory_to_restore" `
  --journal "D:\.AI\work\memory_to_restore\dziennik.json" `
  --music "D:\.AI\work\memory_to_restore\analizy_utworow.json" `
  --baseline "D:\.AI\work\memory_test03" `
  --recursive
```

Raport trafia domyślnie do:

```text
<katalog bazy>\memory_rebuild_reports\
```

`plan` importuje wszystko do tymczasowej kopii, uruchamia walidację i Test04, a następnie usuwa bazę tymczasową.

## 2. Nowa baza od zera

Jeżeli plik jeszcze nie istnieje:

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 build `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --source-dir "D:\.AI\work\memory_to_restore" `
  --recursive
```

Jeżeli istniejący plik ma zostać świadomie zastąpiony nową odbudową:

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 build `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --source-dir "D:\.AI\work\memory_to_restore" `
  --recursive `
  --overwrite
```

Przed przebudową tworzony jest snapshot istniejącej bazy.

## 3. Kontynuacja istniejącego TEST04

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 build `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --source-dir "D:\.AI\work\nowe_eksporty" `
  --recursive `
  --resume
```

`--resume` zaczyna od spójnego snapshotu obecnej bazy i publikuje wynik dopiero po walidacji.

## 4. Jawna migracja starej bazy

Stare SQLite nie są automatycznie zbierane z katalogu. Trzeba podać je jawnie:

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 build `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --legacy-db "D:\PRIVATE\TEST03\memory_jazn.sqlite3" `
  --source-dir "D:\.AI\work\memory_to_restore" `
  --recursive
```

Baseline można wskazać osobno przez `--baseline`; baseline jest wtedy tylko kontrolą regresji i nie jest importowany.

## 5. Kandydaci po pełnym L0

Opcjonalnie:

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 build `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --source-dir "D:\.AI\work\memory_to_restore" `
  --recursive `
  --resume `
  --generate-candidates
```

To **nie** zatwierdza doświadczeń automatycznie i nie promuje L2/L3.

## 6. Walidacja

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 validate `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --baseline "D:\.AI\work\memory_test03"
```

## 7. Dopisywanie bieżącego stanu afektywnego

Przykład ręczny:

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 append-affect `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --source-type runtime_turn `
  --source-id "turn-20260822-001" `
  --event-time "2026-08-22T04:00:00+02:00" `
  --emotions "spokój" `
  --emotions "ciekawość" `
  --feelings "poczucie ciągłości" `
  --impressions "ważna rozmowa" `
  --reflection "Chcę zachować ten stan jako źródłowy rekord operacyjny." `
  --context "Rozmowa z Krzysztofem"
```

Można też przekazać cały rekord JSON przez stdin:

```powershell
Get-Content .\affect.json -Raw |
  py -X utf8 .\tools\memory_rebuild.py stage4 append-affect `
    --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
    --stdin-json
```

Rekord jest zapisywany w `affective_observations` i równolegle projektowany do dziennika L0.

## 8. Synchronizacja bieżącego runtime

Obecny runtime Jaźni zapisuje ważne ślady także do:

```text
memory\raw\dziennik.json
memory\layered\*.jsonl
```

Stage4 może przyrostowo wciągać te pliki do jednej bazy:

```powershell
py -X utf8 .\tools\memory_rebuild.py stage4 sync-runtime `
  --database "D:\.AI\work\memory_test04\memory_jazn.sqlite3" `
  --runtime-root "D:\.AI\jazn_latka_master"
```

Ta operacja również używa stagingu i `--resume` wewnętrznie.

**Ważne:** `sync-runtime` jest bezpiecznym mechanizmem synchronizacji, ale sam nie uruchamia się automatycznie w daemonie. Jeżeli zapis do `memory_jazn.sqlite3` ma następować po każdej turze bez ręcznego wywołania, trzeba jeszcze podłączyć ten sink do `RuntimeMemoryWriter`/runtime persistence.

## Instalacja

1. Zrób checkpoint Git/backup.
2. Zachowaj `tools\memory_rebuild_legacy_v24.py`.
3. Zastąp:
   ```text
   tools\memory_rebuild.py
   ```
   dostarczonym plikiem.
4. Sprawdź:
   ```powershell
   py -X utf8 .\tools\memory_rebuild.py stage4 --help
   py -X utf8 .\tools\memory_rebuild.py legacy --self-test
   ```
5. Najpierw uruchom `stage4 plan`.
6. Dopiero po poprawnym raporcie uruchom `stage4 build`.

## Granica TEST04

Narzędzie nie modyfikuje aktywnego `memory/` runtime i nie aktywuje pamięci systemowej. Jego celem jest zbudowanie i zweryfikowanie finalnego `memory_jazn.sqlite3`, który dopiero później może przejść osobny proces instalacji/recovery/wake.


## Głębokie drzewa rozmów HTML

W aktualnej linii v15.4.3.1 `chat_export_reader._structural_order()` może wejść w
`RecursionError` na bardzo głębokim drzewie rozmowy. Stage4 instaluje w procesie
importu iteracyjny preorder traversal (jawny stos), zachowujący kolejność
parent-before-children bez zależności od limitu rekurencji Pythona.

Poprawka została sprawdzona na rzeczywistym eksporcie
`chatGPT-export-16.06.2025.html`: 21 rozmów, 3829 węzłów i 3270 dokumentów FTS.
