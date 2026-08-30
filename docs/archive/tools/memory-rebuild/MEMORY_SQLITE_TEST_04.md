# Memory SQLite Test nr 4 — kompletny protokół operatorski

## Cel

Memory SQLite Test nr 4 jest lokalnym, powtarzalnym protokołem odbudowy i
walidacji pięciu baz developerskich z wszystkich posiadanych eksportów ChatGPT,
w tym z najnowszego eksportu wykonanego bezpośrednio przed właściwym testem.

Kanoniczny operator Windows PowerShell:

```powershell
& ".\tools\Invoke-JaznMemorySqliteTest04.ps1"
```

Operator jest cienkim koordynatorem. Używa istniejących:

- `MemoryRestoreOrchestrator` do narastającego planu, backupu i rebuildów;
- `ChatExportReader` i `ChatExportImporter` do rozpoznawania i deduplikacji;
- `MemoryRebuildCoordinator` do statusu, verify i recall;
- `MemoryValidationTarget` do pełnej kontroli każdej z pięciu SQLite.

Operator nie kopiuje schematów SQLite, importerów ani klasyfikatorów. Nie
aplikuje historycznego patcha
`restore_memory_v24.0.1_plan_copy_save_cumulative.patch`. Bieżący Memory Rebuild
`24.0.2.05` pozostaje źródłem kontraktów planu i importu.

## Granica prawdy

Warstwy są rozłączne:

| Warstwa | Znaczenie w Teście 04 |
|---|---|
| L0 | Prywatne eksporty, dziennik i inne jawnie zatwierdzone źródła |
| Pięć baz rebuild | Developerski wynik Testu 04, poza repozytorium |
| Pamięć testowa | `TargetRoot` oraz drugi świeży `TargetRoot_rebuild_b` |
| Pamięć aktywnego runtime | Nie jest celem rebuilda i nie jest modyfikowana |
| L1 | Pamięć robocza sesji; Test 04 jej nie aktywuje |
| L2 | Pamięć krótkoterminowa; automatyczna promocja pozostaje wyłączona |
| L3 | Pamięć długoterminowa; wymaga osobnego manifestu i jawnej decyzji |

`integrity_check=ok`, kod wyjścia importera `0`, istniejące rozmowy, trafienia
recall, daemon albo wake-state nie wystarczają do stwierdzenia gotowej pamięci.
Raport końcowy ocenia osobno integralność, kompletność źródeł, idempotencję,
odtwarzalność, reconciliation Testu 03, recall, test wieloturowy, restart, L2 i
L3.

Test 04:

- nie zapisuje do aktywnego `memory/`;
- nie używa `workspace_runtime/` jako bazy docelowej;
- nie wywołuje `approve-l3-manifest-sha`;
- nie promuje doświadczeń, L2 ani L3;
- nie aktywuje pamięci systemowej;
- zawsze pozostawia `system_activation_ready=false`.

## Wymagania

1. Branch musi być dokładnie `feature/memory-sqlite-test-04`.
2. Domyślnie śledzony worktree musi być czysty.
3. `TargetRoot` musi leżeć poza repozytorium.
4. Prywatny manifest musi mieć schemat
   `jazn_memory_sqlite_test04_sources/v1`.
5. Pełny rebuild wymaga istniejącego baseline Testu 03 i osobnego katalogu
   legacy `v15.0.3.222`.
6. Recall wymaga co najmniej jednego rzeczywistego przypadku
   `jazn_private_recall_cases/v1`.
7. Prywatne pliki pozostają wyłącznie lokalnie.

`-AllowDirty` jest jawnym wyjątkiem operatorskim. Nie osłabia walidacji źródeł
ani zakazu zapisu prywatnych danych do Git.

## Przygotowanie szablonów prywatnych

```powershell
& ".\tools\Invoke-JaznMemorySqliteTest04.ps1" `
  -Root . `
  -WriteTemplates
```

Kopie powstaną pod:

```text
workspace_runtime/memory_sqlite_test_04/
```

Źródła wersjonowanych, pustych szablonów są w:

```text
docs/templates/memory_sqlite_test_04/
```

Nie edytuj wersjonowanego szablonu danymi prywatnymi. Skopiuj lokalną wersję do
nazwy `source-manifest.private.json`, `recall-cases.private.json` i, po ręcznym
teście, `multi-turn-review.private.json`.

## Najnowszy eksport przed testem

Bezpośrednio przed zamrożeniem manifestu:

1. Zleć w ChatGPT nowy eksport danych.
2. Poczekaj na zakończenie generowania i pobierz pełne archiwum.
3. Nie rozpakowuj ani nie modyfikuj archiwum.
4. Umieść je w prywatnym katalogu razem z wcześniejszymi eksportami.
5. Dodaj je jako ostatni eksport ChatGPT w manifeście.
6. Ustaw wyłącznie dla niego `latest_export=true`.
7. Uzupełnij opisową datę `exported_at`, jeżeli data nie wynika jednoznacznie
   z nazwy.
8. Dopiero po sprawdzeniu kompletności ustaw trzy pola
   `operator_attestation` na `true`.

Operator nie może sam udowodnić, że na innym dysku nie istnieje pominięty
eksport. Dlatego kompletność wymaga jawnej atestacji operatora.

## Prywatny manifest źródeł

Minimalny kształt:

```json
{
  "schema_version": "jazn_memory_sqlite_test04_sources/v1",
  "operator_attestation": {
    "all_known_chatgpt_exports_included": true,
    "latest_export_created_immediately_before_test": true,
    "source_order_reviewed": true
  },
  "baseline_test03_root": "D:\\PRIVATE\\jazn_memory_test_03",
  "legacy_memory_root": "D:\\PRIVATE\\latka_v15.0.3.222",
  "baseline_decline_justifications": {},
  "sources": [
    {
      "ordinal": 1,
      "role": "chatgpt_export",
      "path": "D:\\PRIVATE\\export-2025-01-01.zip",
      "exported_at": "2025-01-01",
      "latest_export": false,
      "pipeline": "memory_rebuild",
      "approved": true
    },
    {
      "ordinal": 2,
      "role": "chatgpt_export",
      "path": "D:\\PRIVATE\\export-latest.zip",
      "exported_at": "2026-07-26",
      "latest_export": true,
      "pipeline": "memory_rebuild",
      "approved": true
    },
    {
      "ordinal": 3,
      "role": "journal",
      "path": "D:\\PRIVATE\\dziennik.json",
      "exported_at": null,
      "latest_export": false,
      "pipeline": "memory_rebuild",
      "approved": true
    }
  ]
}
```

Zasady:

- `ordinal` jest jawny, ciągły i zgodny z kolejnością tablicy;
- kolejność nie wynika z rozmiaru pliku;
- dziennik znajduje się po źródłach rozmów;
- `approved_l0` wymaga `approved=true`;
- `html_only_review` przyjmuje wyłącznie jawny plik `.html`/`.htm`, nie trafia do
  pięciu baz Memory Rebuild i wymaga osobnej, bezpiecznej fazy `-RunHtmlDryRun`;
- baseline Testu 03 i legacy nie są importowane jako kolejne rozmowy.

Przed planem operator zapisuje prywatnie rozmiar, SHA-256, rozpoznany typ,
kanoniczne członki, CRC, szyfrowanie, traversal, symlinki, duplikaty oraz
kolizje wielkości liter. Identyczne SHA są deduplikowane przed importem z
zachowaniem pierwszej pozycji.

## Kontrakt eksportu ChatGPT

1. `conversations.json` jest kanonicznym źródłem rozmów.
2. `conversations-001.json`, `conversations-002.json` itd. są czytane
   numerycznie jako części jednego eksportu.
3. `shared_conversations.json` jest tylko metadanymi linków.
4. `chat.html` jest pomocniczą mapą załączników przy kanonicznym JSON.
5. Rekord bez niepustego `mapping` jest metadanymi, nie rozmową.
6. Identyczne archiwa są wykrywane po SHA przed importem.
7. Powtarzające się rozmowy przechodzą przez istniejącą deduplikację.
8. Rozbieżne wersje tego samego ID są konfliktem wymagającym kontroli.
9. Jawna kolejność źródeł ma pierwszeństwo.
10. Plan zamraża SHA-256 i rozmiar. Zmiana któregokolwiek blokuje wykonanie.

ZIP z path traversal, symlinkiem, szyfrowaniem, błędem CRC, duplikatem ścieżki
albo kolizją wielkości liter jest blokowany przed importem.

## Faza HTML — bezpieczny dry-run istniejącego importera

Źródła z `pipeline=html_only_review` są sprawdzane przez istniejący
`HtmlMemoryIngestor`, a nie przez nowy parser i nie przez pięć baz Memory Rebuild.
Faza wymaga jawnej flagi:

```powershell
& ".\tools\Invoke-JaznMemorySqliteTest04.ps1" `
  -Root . `
  -SourceManifest ".\workspace_runtime\memory_sqlite_test_04\source-manifest.private.json" `
  -TargetRoot "D:\PRIVATE\jazn_memory_test_04" `
  -PlanOnly `
  -RunHtmlDryRun
```

Opcjonalne `-HtmlLimitConversations 100` ogranicza pierwszą próbę na dużym HTML.
Raport `html-import-dry-run.sanitized.json` zawiera wyłącznie status, SHA, rozmiar
i liczniki. Nie zapisuje ścieżek, nazw, pytań ani treści rozmów. Dry-run potwierdza
też, że docelowa baza recovered-memory nie została utworzona ani zmieniona.

Pełny import HTML pozostaje osobnym, świadomym krokiem operatorskim przez
`run.py memory-import-html`; Test 04 nie uruchamia go automatycznie i nie promuje
L2 ani L3.

## Faza A — plan-only

Wybierz nieistniejący `TargetRoot`:

```powershell
& ".\tools\Invoke-JaznMemorySqliteTest04.ps1" `
  -Root . `
  -SourceManifest ".\workspace_runtime\memory_sqlite_test_04\source-manifest.private.json" `
  -TargetRoot "D:\PRIVATE\jazn_memory_test_04" `
  -PlanOnly
```

Plan:

- nie tworzy `TargetRoot`;
- używa tymczasowej SQLite;
- symuluje źródła narastająco;
- zapisuje dokładny `plan.json` i czytelny `plan.txt`;
- zachowuje faktyczne relacje Memory Rebuild, np. `new`, `identical`,
  `older_subset`, `extends_active` albo `identical_export_duplicate`;
- kończy się niezerowym kodem, gdy źródło lub atestacja jest niepoprawna.

## Fazy B–G — pełny przebieg developerski

Przygotuj prywatne przypadki recall bez wpisów szablonowych, następnie:

```powershell
& ".\tools\Invoke-JaznMemorySqliteTest04.ps1" `
  -Root . `
  -SourceManifest ".\workspace_runtime\memory_sqlite_test_04\source-manifest.private.json" `
  -TargetRoot "D:\PRIVATE\jazn_memory_test_04" `
  -RecallCases ".\workspace_runtime\memory_sqlite_test_04\recall-cases.private.json" `
  -RunRebuild `
  -RunIdempotence `
  -RunFreshRebuildComparison `
  -RunRecall
```

Ścieżki baseline można podać w manifeście albo jawnie:

```powershell
-BaselineTest03Root "D:\PRIVATE\jazn_memory_test_03" `
-LegacyMemoryRoot "D:\PRIVATE\latka_v15.0.3.222"
```

Jeżeli te same ścieżki podano w obu miejscach, muszą być identyczne. Operator
nie wybiera po cichu jednej z rozbieżnych wartości.

Pierwszy rebuild powstaje w katalogu staging na tym samym woluminie. Po
zamknięciu uchwytów i pełnej walidacji katalog jest atomowo przemianowany na
`TargetRoot`. Zawiera dokładnie pięć baz:

```text
memory/sqlite/archive_chats.sqlite3
memory/sqlite/journal.sqlite3
memory/sqlite/experience.sqlite3
memory/sqlite/memory_jazn.sqlite3
memory/sqlite/import_catalog.sqlite3
```

Ustawienia są stałe:

- `verify_after_each=true`;
- `full_validation=true`;
- `continue_on_error=false`;
- `create_backup=true`;
- `audit_classifiers=true`;
- `reclassify_journal_dry_run=true`;
- `apply_reclassification=false`;
- `analyse_topics=false`;
- `candidate_limit=0`;
- brak automatycznego doświadczenia, L2, L3 i analizy mediów.

Pierwszy pełny przebieg automatyczny kończy się kodem `2` i stanem
`awaiting_manual_multi_turn_review`, dopóki operator nie dołączy ręcznej oceny
wieloturowej `passed`. Jest to oczekiwane zachowanie fail-closed, a nie utrata
wyniku rebuilda.

Pominięcie `-RunIdempotence`, `-RunFreshRebuildComparison` albo `-RunRecall`
pozostawia odpowiednie pole `not_run` i blokuje kod końcowy `0`. Te flagi
umożliwiają diagnostyczne uruchomienie fazy, lecz nie pozwalają ogłosić
kompletnego Testu 04.

## Idempotencja

`-RunIdempotence` uruchamia te same zamrożone źródła na pierwszym celu.
Porównywane są:

- schematy;
- stabilne liczniki;
- logiczne hashe wierszy;
- brak kandydatów doświadczeń;
- brak L2 i L3.

SHA całego pliku SQLite nie jest kryterium, ponieważ układ stron i metadane
techniczne mogą się zmieniać. Przyrost tabeli audytowej
`import_catalog.operations` jest jawnie raportowaną różnicą techniczną, a nie
duplikatem pamięci.

## Drugi świeży rebuild

`-RunFreshRebuildComparison` tworzy:

```text
<TargetRoot>_rebuild_b
```

Oba świeże wyniki muszą mieć te same schematy, pełne liczniki tabel i logiczne
fingerprinty. Każda różnica jest wypisana; nie ma ogólnej tolerancji.

## Baseline Testu nr 3

Znany baseline:

- 474 rozmowy;
- 65 285 węzłów;
- 49 650 dokumentów FTS;
- 519 wpisów dziennika;
- L2 = 0;
- L3 = 0.

Test 04 może mieć większe liczniki. Raport rozdziela zachowane, nowe, scalone,
pominięte i konflikty. Brakujące lub zmienione rekordy baseline oraz spadki
liczników blokują wynik, chyba że prywatny manifest zawiera konkretną
`baseline_decline_justifications` dla dokładnej metryki. Raport udostępnialny
zapisuje wtedy wyłącznie SHA uzasadnienia.

## Pełna walidacja SQLite

Układ pięciu baz Memory Rebuild nie jest pełnym układem aktywnego runtime.
Dlatego operator nie interpretuje brakujących runtime shardów jako błędu pięciu
baz. Dla każdej z nich wywołuje ten sam walidator SQLite w trybie:

- `integrity_check`;
- `foreign_key_check`;
- `table_counts`;
- `hash_files`;
- metryki stron i schematu.

Dodatkowo wymaga braku pozostałych WAL/SHM/journal i plików tymczasowych,
ponownego otwarcia każdej bazy oraz poprawnych manifestów backupu.

Na pełnym, osobnym runtime można dodatkowo uruchomić:

```powershell
py -X utf8 .\run.py memory-validate --root <PEŁNY_RUNTIME_ROOT> `
  --full --include-all-sqlite --table-counts --hash-files `
  --output workspace_runtime/memory_validation/test04-runtime.json `
  --json --progress
```

Nie należy używać braku niepowiązanych runtime shardów do fałszywego oblania
developerskiego zestawu pięciu baz.

## Recall

Format pozostaje `jazn_private_recall_cases/v1`. Operator obsługuje:

- `expected_any`;
- `expected_all`;
- `forbidden_any`;
- `expected_sources`;
- `minimum_hits`;
- `limit`.

Raport `recall.sanitized.json` zawiera tylko SHA pytania i ID, liczniki,
brakujące dopasowania, fałszywe dopasowania oraz wynik warunków. Nie zawiera
pytań, oczekiwanych terminów ani treści wyników.

Brak rzeczywistego przypadku recall albo pozostawiony tekst szablonowy blokuje
`-RunRecall`.

## Faza H — test wieloturowy

Każdy run tworzy `multi-turn-review.template.json`. Skopiuj go do prywatnej
nazwy, dodaj scenariusz tur i wykonaj rozmowę ręcznie. Oceń:

1. odwołanie do wcześniejszego faktu;
2. utrzymanie tematu przez kilka tur;
3. brak mieszania wspomnień;
4. źródło i provenance;
5. brak zamiany sceny książkowej w zdarzenie fizyczne;
6. brak zamiany snu lub wizji w fakt;
7. brak konfabulacji po braku trafienia;
8. jawne powiedzenie, że wspomnienia nie znaleziono.

Ustaw `overall_status` na `passed`, `failed` albo `not_reviewed`. `passed`
wymaga wszystkich ośmiu pól `checks=true`, niepustego `reviewed_by` oraz
prawidłowego, strefowego czasu ISO 8601 w `reviewed_at_utc`. Automat nigdy sam
nie ogłasza naturalności rozmowy.

Wynik można dołączyć przy wznowieniu:

```powershell
& ".\tools\Invoke-JaznMemorySqliteTest04.ps1" `
  -Root . `
  -SourceManifest ".\workspace_runtime\memory_sqlite_test_04\source-manifest.private.json" `
  -TargetRoot "D:\PRIVATE\jazn_memory_test_04" `
  -RecallCases ".\workspace_runtime\memory_sqlite_test_04\recall-cases.private.json" `
  -MultiTurnReview ".\workspace_runtime\memory_sqlite_test_04\multi-turn-review.private.json" `
  -RunRebuild -RunIdempotence -RunFreshRebuildComparison -RunRecall -Resume
```

## Faza I — restart i wake-state

Restart jest wyłączony domyślnie. Nie dotyczy developerskiego `TargetRoot`, lecz
jawnie wskazanego `Root` aktywnego runtime. Wymaga przed restartem
`active_trusted`.

```powershell
& ".\tools\Invoke-JaznMemorySqliteTest04.ps1" `
  <pozostałe parametry pełnego runu> `
  -RestartDaemon `
  -RestartTimeoutSeconds 90 `
  -Resume
```

Operator zapisuje przed i po:

- ID i SHA wake-state;
- SHA checkpointu, poprzednika i pliku;
- generację i licznik tur;
- PID, stan endpointu i heartbeat;
- zgodność aktywnego rootu.

Przechodzi wyłącznie przy tym samym kwalifikującym się wake-state oraz tym
samym checkpointcie albo prawidłowym następcy. Niezgodność hashy nie może
odziedziczyć carryover ani ominąć truth gate.

## Faza J — L2 i L3

Test 04 nie tworzy kandydatów (`candidate_limit=0`) i nie tworzy manifestu L3.
`l3-status.json` rozróżnia:

- `manifest_created`;
- `manifest_reviewed`;
- `manifest_approved`;
- `promotion_executed`.

Bez osobnego jawnego polecenia zatwierdzenie i promocja pozostają `false`.
Issue #59 pozostaje otwarte do rzeczywistego prywatnego przebiegu, ręcznej
rozmowy i osobnej decyzji L3.

## Wznowienie

Każda ukończona faza ma atomowy raport i wpis w prywatnym
`state.private.json`.
`-Resume` wybiera najnowszy run o tym samym SHA manifestu i tym samym
`TargetRoot`.

Po przerwaniu:

1. Nie usuwaj stagingu w ciemno.
2. Sprawdź `events.jsonl` i raport ostatniej fazy.
3. Potwierdź, że źródła nie zostały zmienione.
4. Uruchom tę samą komendę z `-Resume`.

Rebuild na częściowym stagingu jest idempotentny. Istniejący opublikowany cel
jest akceptowany przy wznowieniu tylko po pełnej walidacji pięciu baz.

## Raporty

Prywatny katalog UTC:

```text
workspace_runtime/memory_sqlite_test_04/<RUN_ID>/
```

Minimalny zestaw:

```text
settings.private.json
source-inventory.private.json
source-inventory.sanitized.json
plan.json
plan.txt
events.jsonl
preflight.json
first-rebuild-summary.json
same-target-idempotence.json
fresh-rebuild-comparison.json
test03-baseline-comparison.json
sqlite-full-validation.json
recall.sanitized.json
html-import-dry-run.sanitized.json
restart-continuity.json
multi-turn-review.template.json
l3-status.json
summary.private.json
summary.sanitized.json
```

Raport sanitizowany nie zawiera pełnych ścieżek, nazw eksportów, pytań recall,
oczekiwanych terminów, fragmentów rozmów, tytułów, treści dziennika, sekretów,
tokenów ani danych osobowych. Prywatne raporty pozostają lokalne i nie mogą
trafić do Git.

## Interpretacja końcowa

`summary.sanitized.json` zawiera:

```json
{
  "structural_integrity": "passed|failed|not_run",
  "source_completeness": "passed|failed|not_reviewed",
  "same_target_idempotence": "passed|failed|not_run",
  "fresh_rebuild_reproducibility": "passed|failed|not_run",
  "test03_reconciliation": "passed|failed|not_run",
  "recall": "passed|failed|not_run",
  "html_import_dry_run": "passed|failed|not_run|not_applicable",
  "multi_turn_review": "passed|failed|not_reviewed",
  "restart_continuity": "passed|failed|not_run",
  "l2_review": "pending|approved|rejected|not_created",
  "l3_decision": "pending|approved|rejected|not_created",
  "system_activation_ready": false
}
```

Stan `developer_test04_passed` oznacza zaliczenie developerskiego protokołu baz i
wymaganych faz. Nie oznacza aktywacji pamięci, decyzji L3 ani zamknięcia Issue #59.

Zaliczony Test 04 nadal samodzielnie nie aktywuje pamięci systemowej.

## Bezpieczne usunięcie testowych baz

1. Odczytaj z prywatnego raportu dokładne `TargetRoot` i
   `TargetRoot_rebuild_b`.
2. Potwierdź `git branch --show-current` i stan aktywnego markera runtime.
3. Sprawdź, że żaden z celów nie jest repozytorium, jego `memory/`,
   `workspace_runtime/` ani `active_root`.
4. Zamknij wszystkie procesy korzystające z testowych baz.
5. Wykonaj `Test-Path -LiteralPath <DOKŁADNY_CEL>`.
6. Usuń wyłącznie każdą zweryfikowaną, bezwzględną ścieżkę osobnym
   `Remove-Item -LiteralPath <DOKŁADNY_CEL> -Recurse`.
7. Nie używaj globów, zmiennych pustych, katalogu nadrzędnego ani aktywnego
   runtime jako celu.

Usunięcie jest nieodwracalne, jeśli katalog nie znajduje się w koszu. Zachowaj
raporty i prywatny manifest do czasu ręcznej akceptacji wyniku.
