# Memory Rebuild Studio P0 — interfejs użytkownika

## Cel P0

P0 porządkuje istniejące funkcje Memory Rebuild bez tworzenia drugiego silnika pamięci. Główna aplikacja pełnoekranowa ma trzy stałe strony:

1. **TESTY** — profile Test 01, 02, 03, 04 oraz Final;
2. **PROJEKTOWANIE** — projekt, źródła, baza docelowa, import, kandydaci, plan bez zapisu, porównanie baseline i finalny eksport;
3. **USTAWIENIA** — pełny przegląd opcji projektu, ustawień retrieval/FTS/embeddingów, blokad bezpieczeństwa, ścieżek i wyglądu.

Interfejs jest zbudowany na istniejącym `prompt_toolkit`. Kod prezentacji jest rozdzielony na:

- `theme.py` — semantyczne tokeny motywu;
- `themes.py` — konkretne palety i mapowanie do stylu `prompt_toolkit`;
- `layout.py` — kompozycja pełnoekranowego layoutu;
- `studio_p0.py` — stan stron, nawigacja, skróty i routing do istniejących workflow.

Domyślna paleta `latka-terminal` jest inspirowana przekazanym przykładem terminalowej aplikacji: ciemne granatowe tło, ciepłe brzoskwiniowe obramowania/akcenty, lawendowe zaznaczenia i oszczędne kolory statusu.

## Uruchomienie

```powershell
py -X utf8 .\tools\rebuild_memory.py studio
```

Zgodnościowo nadal działa:

```powershell
py -X utf8 .\tools\memory_rebuild.py studio
```

Tryb bez pełnoekranowego `prompt_toolkit`:

```powershell
py -X utf8 .\tools\rebuild_memory.py --text-ui studio
```

Opcjonalny plik ustawień silnika:

```powershell
py -X utf8 .\tools\rebuild_memory.py --settings D:\PRIVATE\memory-rebuild-settings.json studio
```

Domyślny katalog prywatnych projektów można ustawić zmienną:

```powershell
[Environment]::SetEnvironmentVariable(
    "JAZN_MEMORY_REBUILD_PROJECTS",
    "D:\PRIVATE\memory_rebuild_projects",
    "User"
)
```

## Nawigacja P0

- `1` — TESTY;
- `2` — PROJEKTOWANIE;
- `3` — USTAWIENIA;
- `Tab` / `→` — następna strona;
- `Shift+Tab` / `←` — poprzednia strona;
- `↑` / `↓` — wybór pozycji;
- `Enter` — otwarcie/uruchomienie wybranej operacji;
- `R` — uruchomienie wybranego profilu na stronie TESTY;
- `T` — przełączenie motywu bieżącej sesji;
- `Q` / `Ctrl+C` — wyjście.

Pełnoekranowy shell tymczasowo oddaje sterowanie istniejącym dialogom projektu/importu/kandydatów/eksportu i po ich zamknięciu wraca na tę samą stronę Studio.

## Strona TESTY

Profile zachowują bieżące kontrakty `test_profiles.py`.

### Test 01 — fundament rozmów

Sprawdza:

- istnienie bazy;
- `PRAGMA integrity_check` i foreign keys;
- jedną fizyczną bazę;
- integralność FTS5 i smoke query;
- obecność rozmów, węzłów i dokumentów FTS;
- brak modyfikacji bazy podczas walidacji.

### Test 02 — rozmowy + dziennik

Test 01 plus:

- `journal_entries > 0`.

### Test 03 — proweniencja i konflikty

Test 02 plus:

- `import_sources > 0`;
- brak nierozwiązanych konfliktów importu, migracji i runtime-sync.

### Test 04 — pełna akceptacja odbudowy

Test 03 plus:

- record-level reconciliation względem baseline'ów;
- source completeness;
- same-target idempotence;
- fresh rebuild reproducibility;
- Test03 reconciliation;
- recall;
- multi-turn review;
- HTML import dry-run, jeśli dotyczy;
- restart continuity dodatkowo przy `system_acceptance=true`.

### Final

Test 04 plus:

- poprawny promotion ledger L2/L3;
- brak automatycznych decyzji/promocji;
- aktywne L3 muszą mieć źródłową decyzję i ledger;
- poprawne zakresy confidence/importance;
- doświadczenia muszą wskazywać istniejących kandydatów.

## Strona PROJEKTOWANIE

P0 nie zastępuje sprawdzonych kontrolerów. Strona grupuje ich funkcje w jeden przepływ:

1. **Projekt i źródła** — edycja projektu, źródeł, baseline'ów, ról, domen prawdy, pipeline'ów i notatek;
2. **Baza docelowa** — wybór jednej kanonicznej `memory_jazn.sqlite3`;
3. **Import źródeł** — rozmowy, HTML, dzienniki i nowe wątki;
4. **Kandydaci pamięci** — podgląd, edycja i jawne decyzje;
5. **Plan bez zapisu** — preflight i dry-run bez uruchomienia odbudowy;
6. **Porównanie z baseline** — baseline'y pozostają tylko do odczytu;
7. **Finalny eksport** — staging finalnej pamięci.

## Strona USTAWIENIA

Widok **Wszystkie ustawienia** pokazuje każde pole `DEFAULT_SETTINGS` projektu oraz każde pole `MemoryRebuildSettings`.

Projekt obejmuje m.in.:

- recursive scan;
- verify after each;
- full validation;
- continue on error;
- backup;
- classifier audit;
- journal reclassification dry-run/apply;
- topic analysis;
- candidate limit;
- progress cadence;
- source hashing i ZIP CRC;
- zachowanie wszystkich branchy i dokładnego tekstu źródeł;
- blokady automatic experience approval / L2 / L3.

Silnik/retrieval pokazuje:

- wymagane FTS5;
- wymagane provenance;
- retrieval limit;
- minimal lexical score;
- stan embeddingów i model;
- wymuszone `automatic_l2=false`, `automatic_l3=false`, `automatic_activation=false`.

Osobne podwidoki pokazują ścieżki projektu/bazy/settings JSON/tool root oraz aktywny theme.

## Folder źródeł

Dla bieżącej odbudowy zalecany folder pozostaje prywatnym katalogiem operatora, np.:

```text
D:\.AI\work\memory_to_restore
```

Skanowanie projektu:

- może obejmować podfoldery i foldery zaczynające się kropką;
- pokazuje pogrupowaną listę znalezionych plików;
- nie dodaje samego folderu jako pliku źródłowego;
- pomija nieobsługiwane sidecary, np. `.sha256`;
- klasyfikuje wejścia do `memory_rebuild`, `html_control`, `catalog_only`, `sqlite_baseline` albo `excluded`.

## Lista źródeł i baseline'ów

Każdy wpis źródła nadal zachowuje kolejność, stan, rozpoznaną rolę, domenę prawdy, pipeline, zatwierdzenie, notatki i dane kontrolne. Usunięcie wpisu z projektu nie usuwa pliku z dysku.

Baseline'y Testów 01–04 są otwierane tylko do odczytu. Można je wyszukiwać, walidować, włączać/wyłączać w porównaniach i usuwać wyłącznie z konfiguracji projektu.

## Granice bezpieczeństwa

- brak automatycznej akceptacji doświadczeń;
- brak automatycznej promocji L2 i L3;
- brak automatycznej aktywacji pamięci;
- brak edycji surowego L0 przez walidację;
- brak zapisu do baseline'ów;
- brak usuwania źródeł i baz z dysku przez operacje listy;
- zapis odbudowy nadal wymaga jawnego kontraktu/potwierdzenia istniejącego workflow;
- pełne dane techniczne pozostają dostępne, ale nie zasłaniają podstawowego interfejsu.
