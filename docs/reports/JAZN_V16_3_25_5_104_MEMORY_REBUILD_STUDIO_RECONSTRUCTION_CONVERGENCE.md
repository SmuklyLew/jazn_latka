# Jaźń v16.3.25.5.104 — Memory Rebuild Studio reconstruction convergence

## Cel

Ta aktualizacja domyka rekonstrukcję Memory Rebuild Studio wokół jednej
kanonicznej `memory_jazn.sqlite3`. Studio nie może publikować bazy tylko dlatego,
że pomocnicza baza protokołu przeszła Test04. Kandydat, który ostatecznie trafia
do `memory/sqlite/memory_jazn.sqlite3`, musi sam przejść migrację, reconciliation,
runtime-native readiness, prywatny Recall Test04 oraz Final.

Zmiana pozostaje fail-closed: nie aktywuje pamięci automatycznie, nie akceptuje
L2/L3 bez jawnej decyzji i nie traktuje raportu z innego runu jako dowodu dla
bieżącego kandydata.

## P0 — Test04 i Final należą do publikowanego kandydata

Kanoniczny przebieg Studio jest teraz rozdzielony na dwie fazy:

1. Test00–03 weryfikują source fidelity, source union, kanoniczne L0,
   projekcje i deterministyczną rekonstrukcję źródeł.
2. Studio tworzy `stage_database`, migruje zweryfikowane snapshoty alpha/legacy,
   importuje bieżący source union, sprawdza idempotencję, integralność,
   reconciliation oraz runtime-native readiness.
3. Test04 wykonuje prywatny benchmark Recall na dokładnie tej `stage_database`.
4. Final wykonuje SQLite Backup API snapshot tej samej bazy.
5. Dopiero po zaliczonym łańcuchu kandydat może zostać opublikowany.

Przejście Test03 → candidate Test04 jest jawne. ProtocolEngine dopuszcza je tylko
z `candidate_reconciliation.ok=true`; zachowuje source fingerprints, lineage
Test03 i rejestruje hash reconciliation. Normalny Test04 bez candidate transition
nadal wymaga identycznej bazy co Test03.

## P0 — acceptance evidence jest związane z konkretnym kandydatem

Raport `jazn_memory_rebuild_acceptance/v3.1` zawiera binding:

- `database_semantic_fingerprint`;
- `source_union_sha256`;
- `restore_run_id`;
- `protocol_run_id`.

Final profile porównuje te wartości z bieżącą bazą. Zielony raport z innego
kandydata, innego source union albo innego runu nie przechodzi.

Fingerprint nie zależy od `unified_memory_meta`, aby nie tworzyć samoodwołania,
ale obejmuje stabilną treść rozmów, dziennika, L0, wariantów, konfliktów,
kandydatów i promotion ledger. Operacyjne timestampy i identyfikatory importu
są wyłączone.

## P0 — runtime systemowy musi być zatrzymany

Studio korzysta z istniejącego `target_preflight()` dla trybu `system`.
Sprawdzenie odbywa się:

- przed rozpoczęciem wykonania;
- ponownie bezpośrednio przed podmianą live SQLite.

Drugi gate zamyka race window, w którym daemon mógłby zostać uruchomiony podczas
długiego Test00–04. Jeśli runtime wróci przed publikacją, operacja kończy się
fail-closed.

## P1 — prepared plan jest pełnym kontraktem wykonania

Plan ma `execution_plan_sha256`. Hash obejmuje między innymi:

- wersję pakietu;
- canonical database;
- source inventory i SHA-256;
- source union;
- stan istniejących baz;
- trwałe sidecary `-wal` i `-journal` istniejącej bazy, jeśli występują;
- prywatny benchmark Test04 i jego SHA-256;
- restart continuity report i SHA-256;
- protocol base commit i tryb system acceptance.

Zmiana któregoś z tych wejść pomiędzy `plan()` i `run()` daje
`prepared_plan_stale`.

Stan `-wal` jest częścią planu, ponieważ w trybie WAL zatwierdzone strony mogą
pozostawać poza głównym plikiem SQLite do checkpointu. `-journal` również jest
wiązaną i rollbackowaną częścią stanu, ponieważ SQLite może pozostawić hot
rollback journal po przerwanym zapisie. `-shm` jest przenoszony przy publikacji,
ale nie fingerprintowany jako trwała treść.

## P1 — reconciliation wykrywa zmianę treści

Dotychczasowe sprawdzenie obecności primary key było za słabe: ten sam klucz
z inną treścią mógł wyglądać na zachowany.

Nowe reconciliation:

- porównuje stable key + content hash;
- pracuje na wspólnych kolumnach source/target, zgodnie z mechaniką migratora;
- ignoruje operacyjne pola czasu/importu;
- toleruje nowe kolumny występujące wyłącznie w unified target;
- zgłasza osobno brakujące klucze i content mismatch.

Dzięki temu ewolucja schematu nie daje fałszywego błędu, ale rzeczywista utrata
lub zmiana zachowywanej treści pozostaje blockerem.

## P1 — atomowy final export i evidence path boundary

`export_final_memory(..., overwrite=True)` ma rollback publikacji:

1. istniejący target jest przenoszony do unikalnego backupu;
2. staging jest przenoszony na target;
3. jeśli drugi replace zawiedzie, stary target jest natychmiast odtwarzany.

Ścieżki acceptance/baseline odczytywane z metadata muszą pozostać wewnątrz
kanonicznego `memory_root`. Absolutny lub względny path escaping poza ten root
jest odrzucany.

## P0 — usunięty circular import runtime

CI ujawniło cykl:

`unified_memory_runtime → memory_rebuild_app.__init__ → application/protocol_engine → unified_memory_runtime`.

Runtime probe jest teraz importowany lokalnie dopiero w operacjach, które
faktycznie go wykonują. Dzięki temu zwykły import runtime i startup nie zależy
od inicjalizacji całej aplikacji Memory Rebuild.

Dodany test uruchamia świeży interpreter i sprawdza import obu warstw, aby
regresja nie wróciła.

## Release identity

Aktywne testy release identity oraz
`latka_jazn/resources/startup_contract.json` zostały zsynchronizowane z
`16.3.25.5.104-memory-rebuild-studio-reconstruction-convergence`.

Historyczny raport v16.3.25.5.103 pozostaje bez zmian.

## Testy regresyjne

`tests/test_memory_rebuild_v24_studio_reconstruction.py` obejmuje między innymi:

- publikację wyłącznie native-unified candidate;
- alpha → beta z immutable baseline;
- Test04/Final na dokładnym publish candidate;
- binding acceptance evidence do candidate/source/run lineage;
- odrzucenie raportu z innego kandydata;
- stale prepared plan po zmianie benchmarku;
- same-key content mismatch;
- zgodną ewolucję schematu z target-only columns;
- path escape poza `memory_root`;
- rollback final publish;
- blokadę aktywnego runtime;
- ponowny runtime gate bezpośrednio przed publikacją;
- brak circular import w świeżym interpreterze.

## Walidacja CI

W toku prac CI wykryło i pomogło usunąć:

- błąd Pyright w nowym teście — poprawiony przez jawne type narrowing bez
  osłabienia konfiguracji;
- P0 circular import runtime — usunięty;
- cztery stare oczekiwania release identity `.103` — zsynchronizowane z `.104`.

Run release-hardening po naprawie circular import i synchronizacji release
identity przeszedł:

- dependency contracts Linux/Windows dla wspieranych wersji Pythona;
- Windows targeted runtime/path tests;
- compile aktywnego Pythona;
- Pyright/static type audit;
- deterministic pack-generator freshness;
- independent semantic route audit;
- cognitive architecture audit;
- host spawn + memory convergence regression set;
- pełny deterministic pytest suite na Ubuntu;
- clean checkout guard.

Dalsze małe hardeningi prepublish runtime gate i WAL plan binding przechodzą
niezależne active-tree Pyright i Stable Test Studio gates; release-hardening
pozostaje źródłem prawdy dla końcowej walidacji HEAD.

## Źródła techniczne

- SQLite Write-Ahead Logging: https://sqlite.org/wal.html
- SQLite temporary files / WAL and shared-memory files:
  https://sqlite.org/tempfiles.html
- Python `os.replace`: https://docs.python.org/3/library/os.html#os.replace
- Python `sqlite3.Connection.backup`:
  https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup

## Granica prawdy

Zielony Memory Rebuild dowodzi integralności i zaakceptowanych właściwości
konkretnego artefaktu pamięci. Nie dowodzi świadomości, biologicznej pamięci ani
prawdziwości każdej historycznej treści źródłowej. Final pozostaje zweryfikowanym
artefaktem wejściowym do osobnego runtime/restore lifecycle; samo utworzenie lub
wyeksportowanie bazy nie aktywuje Jaźni.
