# Jaźń Memory Rebuild v16+ / aplikacja 3.0

`tools/rebuild_memory.py` jest głównym programem operatorskim do przygotowania,
importowania, przeglądania i eksportowania pamięci Jaźni. Poprzedni
`tools/memory_rebuild.py` pozostaje cienkim aliasem zgodnościowym.

Modularny podział kodu, wspólny model L0, adaptery formatów, typowany recall i
bramka prywatnej pamięci są opisane w
[`MEMORY_REBUILD_V16_ARCHITECTURE.md`](MEMORY_REBUILD_V16_ARCHITECTURE.md).

## Najważniejsza zmiana v2.4

Finalnym aktywnym magazynem jest jeden plik:

```text
memory_jazn.sqlite3
```

W tym samym pliku znajdują się logiczne sekcje:

- rozmowy historyczne i nowe wątki;
- pełne drzewa wiadomości, gałęzie i załączniki;
- dziennik i jego rewizje;
- kandydaci pamięci oraz ich rewizje i dowody;
- ręcznie zatwierdzone doświadczenia L1;
- kontrolowane warstwy pamięci roboczej, krótkoterminowej i długoterminowej;
- źródła, operacje, konflikty, walidacje i ledgery decyzji.

Nazwy `archive_chats.sqlite3`, `journal.sqlite3`, `experience.sqlite3` i `import_catalog.sqlite3` pozostają obsługiwane wyłącznie jako stare baseline’y i źródła migracji. Nie są aktywnymi osobnymi magazynami finalnej pamięci.

## Uruchomienie

```powershell
py -X utf8 .\tools\memory_rebuild.py
```

Alternatywny launcher prowadzi do tego samego interfejsu:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py
```

Tryb tekstowy:

```powershell
py -X utf8 .\tools\memory_rebuild.py --text-ui
```

Zależność interfejsu kursorowego:

```powershell
py -X utf8 -m pip install -e ".[memory-rebuild-ui]"
```

## Główne ekrany

1. **Projekty, źródła i baseline’y** — czytelne listy, skan folderów, podgląd, edycja metadanych, wyłączanie i usuwanie wpisu tylko z projektu.
2. **Wybór bazy** — wskazanie istniejącego `memory_jazn.sqlite3` albo utworzenie nowej bazy w wybranym folderze.
3. **Stan bazy** — `integrity_check`, `foreign_key_check`, SHA-256, rozmiar i liczniki.
4. **Import** — eksporty ChatGPT JSON/ZIP, HTML, dzienniki, nowe wątki oraz migracja starych baz.
5. **Kandydaci pamięci** — lista, podgląd, edycja, rewizje, dowody, zatwierdzanie, odrzucanie, łączenie i rozdzielanie.
6. **Profile Testów 01–04 i finalny** — powtarzalne bramki zgodności nad jednym aktualnym silnikiem.
7. **Finalny eksport** — staging, pełna walidacja, manifesty i atomowa publikacja gotowego zestawu.

## Import rozmów

Obsługiwane są:

- `conversations.json`;
- ponumerowane części `conversations-001.json`, `conversations-002.json`, ...;
- ZIP-y eksportu ChatGPT;
- HTML z osadzonym `var jsonData = ...`;
- kontrolny wariant HTML z widoczną strukturą:

```html
<div class="conversation">
  <h4>Nazwa okna czatu</h4>
  <pre class="message">...</pre>
</div>
```

Gdy HTML zawiera osadzone `jsonData`, importer zachowuje pełne drzewo rozmowy. Wariant `div/pre` jest kontrolowanym fallbackiem i może odtworzyć tylko widoczną kolejność wiadomości.

Import jest przyrostowy. Ten sam eksport jest rozpoznawany po SHA-256, a rozmowy są deduplikowane po identyfikatorach i strukturze. Nowe wątki można dopisywać później do tego samego `memory_jazn.sqlite3` bez pełnej odbudowy od zera.

## Plan bez zapisu

`unified-import --dry-run` i plan migracji działają na tymczasowej kopii bazy. Docelowy plik nie jest zmieniany. Kolejne źródła w planie widzą wynik wcześniejszych źródeł, więc raport odzwierciedla rzeczywistą kolejność importu.

## Migracja Testów 01–04

Stare bazy pozostają nienaruszone. Migrator:

1. wyszukuje znane pliki SQLite;
2. tworzy plan tabel i liczników;
3. kopiuje kompatybilne rekordy przez `INSERT OR IGNORE` w kolejności zależności;
4. odbudowuje indeksy FTS;
5. wykonuje pełny `integrity_check` i `foreign_key_check`.

CLI:

```powershell
py -X utf8 .\tools\memory_rebuild.py unified-migrate `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3 `
  --legacy-root D:\PRIVATE\jazn_memory_tests
```

Plan bez zapisu:

```powershell
py -X utf8 .\tools\memory_rebuild.py unified-migrate `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3 `
  --legacy-root D:\PRIVATE\jazn_memory_tests `
  --dry-run
```

## Kandydaci pamięci

Generowanie kandydatów nie zatwierdza ich automatycznie. Każda ręczna edycja zapisuje poprzedni stan w `candidate_revisions`.

Dostępne operacje:

- filtrowanie i wyszukiwanie;
- edycja tytułu, treści, rodzaju prawdy, pewności, ważności i domen;
- dodawanie dokładnych fragmentów źródłowych i kontekstu przed/po;
- zatwierdzenie do doświadczenia L1;
- odrzucenie albo przywrócenie do przeglądu;
- połączenie kilku kandydatów;
- rozdzielenie części treści do osobnego kandydata.

Zatwierdzenie kandydata nie promuje go automatycznie do L2 ani L3.

## Profile testowe

```text
test01  — integralność, jedna baza, rozmowy, węzły i wyszukiwanie
test02  — wymagania Testu 01 + dziennik
test03  — wymagania Testu 02 + proweniencja i brak nierozwiązanych konfliktów
test04  — wymagania Testu 03 + porównanie z baseline’ami
final   — nadzbiór Testów 01–04 + kontrola kandydatów i doświadczeń
```

Test finalny nie uruchamia czterech importerów po kolei. Używa jednego aktualnego silnika i sprawdza, czy wynik spełnia wymagania historycznych testów.

Przykład:

```powershell
py -X utf8 .\tools\memory_rebuild.py test-profile `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3 `
  --profile final `
  --baseline D:\PRIVATE\jazn_memory_tests
```

## Finalny eksport

Eksport powstaje najpierw w katalogu stagingowym. Po powodzeniu zawiera:

```text
memory_jazn.sqlite3
source-manifest.json
test-profile-final.json
candidate-review-ledger.json
promotion-ledger.json
database-manifest.json
final-export-summary.json
```

Baza jest kopiowana przez SQLite Backup API, po czym przechodzi pełną walidację. Publikacja katalogu jest atomowa. Istniejący cel nie jest zastępowany bez jawnego `--overwrite`; stary katalog jest wtedy przenoszony do backupu.

```powershell
py -X utf8 .\tools\memory_rebuild.py final-export `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3 `
  --output D:\PRIVATE\jazn_memory_final `
  --baseline D:\PRIVATE\jazn_memory_tests
```

## Najważniejsze komendy CLI

Utworzenie bazy:

```powershell
py -X utf8 .\tools\memory_rebuild.py unified-init `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3
```

Import źródeł:

```powershell
py -X utf8 .\tools\memory_rebuild.py unified-import `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3 `
  D:\.AI\work\memory_to_restore\export.zip `
  D:\PRIVATE\jazn_memory_sources\journal_from_sqlite.jsonl
```

Plan importu:

```powershell
py -X utf8 .\tools\memory_rebuild.py unified-import `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3 `
  --dry-run `
  D:\.AI\work\memory_to_restore\export.zip
```

Walidacja:

```powershell
py -X utf8 .\tools\memory_rebuild.py unified-validate `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3
```

Spójny backup:

```powershell
py -X utf8 .\tools\memory_rebuild.py unified-backup `
  --database D:\PRIVATE\jazn_memory\memory_jazn.sqlite3 `
  --output D:\PRIVATE\jazn_memory_backups
```

Tryb pięciobazowy pozostaje dostępny dla regresji:

```powershell
py -X utf8 .\tools\memory_rebuild.py legacy --self-test
```

## Granice bezpieczeństwa

- surowe rozmowy i dzienniki L0 nie są edytowane;
- usunięcie wpisu w projekcie nie usuwa pliku z dysku;
- brak automatycznej akceptacji doświadczeń;
- brak automatycznej promocji L2 i L3;
- sceny książkowe, roleplay, sny i wyobraźnia zachowują własny rodzaj prawdy;
- plan nie zapisuje do docelowej bazy;
- finalny eksport nie aktywuje runtime;
- sama obecność bazy pamięci nie dowodzi działania Jaźni.
