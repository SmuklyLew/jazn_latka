# Modernizacja rodziny Studio Jaźni — rejestr wykonania

Powiązane zgłoszenie: https://github.com/SmuklyLew/jazn_latka/issues/340

## Zakres i granice

Realizacja obejmuje wszystkie siedem aplikacji: Konfiguracja, Pamięć, Testy,
Pack Generator, Dependency Studio, Python Runtime Studio i Studio Przebudowy
Wersji. Poniższy checkpoint nie oznacza zakończenia P0 ani całego celu.
Nie wykonujemy merge, force-push, importu prywatnej MEMORY ani płatnych API.
Testy korzystają z syntetycznych danych. Runtime pozostaje właścicielem
control plane i finalizacji. Nie obniżamy native_unified_required.

## Baseline 2026-10-10

- Zweryfikowany origin/master: `48168b74ccfce42318c2568fbc78433c6051a0d5`.
- SYSTEM: `16.3.25.5.115.18.1`; Configuration Studio 1.0, Memory Studio 3.1,
  Test Studio 1.3.0, Pack Generator 10.1.86.0.116, Version Rebuild 0.2.
  Dependency/Python Studio korzystają z CommandStudioSpec i wersji SYSTEM.
- Checkpoint Git: `checkpoint/studios-baseline-20261010`.
- Worktree: `D:\.AI\jazn_branchs\studios-p0-integrity-memory-paths`.
- Branch: `fix/studios-p0-integrity-memory-paths`, utworzony z origin/master.
- Otwarte PR-y #262 i #319 sprawdzone; nie przejęto ich historii ani zakresu.
- Python 3.14.4, pytest 9.1.1, Tk 8.6. Testy początkowe: 34 PASS, 2 SKIPPED.
- Pełny baseline pytest: przerwany po zatrzymaniu postępu na 44%, po
  potwierdzeniu żywych procesów. Nie ma końcowego PASS. Procesy zakończone.
- Pyright 1.1.411 z jawnym venv: 21 błędów brakujących opcjonalnych importów
  MCP/Starlette/Uvicorn, 1 ostrzeżenie. Pierwsza próba bez jawnego interpretera
  wywołała Windows Python Install Manager i nie stanowi miarodajnego gate.
- Osobny venv zadania z extras archive,memory-rebuild-ui,mcp-http oraz
  PyInstaller utworzony poza repo. TEMP/TMP również poza SYSTEM.

## Kolejność i kryteria etapów

| Etap | Zakres | Stan |
| --- | --- | --- |
| P0 | Bezpieczne logi/ustawienia/recenzje; wspólna normalizacja MEMORY/SQLite; preflight schematu; regresje integralności | IN_PROGRESS |
| P1 | Konfiguracja: rejestr ról, wartości domyślne/zapisane/efektywne, pochodzenie, dry-run/diff, aktywacja; Pamięć: źródło/cel/staging/active, inspekcja, porównanie, readiness; Testy: katalog, filtrowanie, historia, eksport, timeout/STOP | NOT RUN |
| P2 | Pełne formularze Dependency i Python Runtime Studio; Pack: przestrzeń, manifest/SHA, etapy walidacji/publikacji, anulowanie | NOT RUN |
| P3 | Podział Version Rebuild na usługi/Git/wersje/config/UI; preflight, checkpoint/rollback, historia; integracja, dokumentacja, GUI/EXE | NOT RUN |

Kolejne etapy mają własne branche i PR-y, stacked gdy zależą od P0.
Każdy wymaga nowej legalnej wersji, kanonicznych metadanych, adekwatnych testów,
commita, pushu i rzeczywistego końcowego CI dla aktualnego HEAD. Otwarty PR ani
częściowy PASS nie oznacza gotowego etapu.

## P0 — implementacja i dowody

- Wspólna normalizacja `memory_path`, runtime storage i tier resolvera:
  historyczny pojedynczy prefiks pozostaje zgodny, podwójny/traversal/drive
  jest odrzucany. Kontrola containment następuje po rozwiązaniu dowiązań.
- `memory_restore_storage` i inspektor używają wspólnego resolvera SQLite.
  Rozróżniamy SYSTEM, MEMORY, sqlite directory i konkretny plik; discovery
  niczego nie tworzy. Jawne fallbacki zachowują historyczny kontrakt klienta.
- `JAZN_MEMORY_TIER_DB` dodane do profilu i allowlisty PowerShell; tylko ścieżka
  względna wewnątrz MEMORY. Picker GUI zapisuje relatywny wybór.
- `database_identity` weryfikuje istniejący schemat w trybie read-only.
  Obca/legacy baza nie staje się native przez nazwę. Runtime install/preflight
  odrzuca obcą bazę przed inicjalizacją tabel.
- Kontrole modułowe po tych zmianach: **89 PASS, 4 SKIPPED** (skipy dotyczą
  niedostępnych uprawnień/capability w sandboxie; nie są PASS).
- Trzy początkowe błędy TemporaryDirectory w testach restore zniknęły po
  wskazaniu zapisywalnego TEMP/TMP; asercji nie zmieniano.
- Pełny pytest, Pyright z pełnymi extras, doctor, package-smoke, Windows EXE,
  synchronizacja metadanych i CI: wymagają potwierdzenia dla finalnego P0 HEAD.

## Uwagi do implementacji kolejnych etapów

Dependency i Python window wymagają dedykowanych stron, bez swobodnego pola
argumentów CLI. Usługi domenowe już istnieją; nie tworzyć nowych silników.
Operacje wykonują się poza Tk; wszystkie StringVar/pickery pozostają w GUI.
Generic CommandStudioSpec close bezwarunkowo terminate'uje proces — nie
stosować tego podczas instalacji, backupu ani publikacji.

Python build `--dry-run-vendor` bez dependency bundle nie jest dry-run całego
build. Select z materialize-root zapisuje pliki. GC Dependency dotyczy
domyślnego environment root, nie dowolnego pola formularza. Kolizje nazw przy
build-set/copy-bundles wymagają preflight. Sukces dopiero po walidacji.

## Procedura wznowienia

### Checkpoint napraw audytu (2026-10-10)

Wypchnięty checkpoint: `7060b05e4bded8ca5386986795b3e046656f2209`
(kod `a72a643eac594e50c24712f65eabda618b82cd45` + kanoniczne metadane).
Draft PR: https://github.com/SmuklyLew/jazn_latka/pull/341.
Metadata check: PASS, manifest/provenance zgodne, 2204 pliki.
Pełny Pyright: PASS, 0 błędów, 1 ostrzeżenie; compileall kodu i aktywnych
testów: PASS. Pełny pytest zebrano 2370 przypadków, przebieg nadal trwa.
CI persistent E2E wykrył pozostawiony stary runtime_version w
deploy/chatgpt_mcp/deployment.contract.json (76 PASS, 1 FAIL).
Poprawka aktualizuje deklarację do bieżącej wersji bez zmian asercji.
Końcowy wynik CI musi zostać sprawdzony ponownie po pushu naprawy.

P0 nadal IN_PROGRESS. Branch i wersja pozostają bez zmian. Przed naprawami
zapisano kopię roboczych plików w lokalnym jazn_checkpoints. Nie odtwarzano ZIP.
Naprawiono również `LivingMemoryGateway._as_sqlite_dir`, kierując go do
wspólnego resolvera. Przywrócono istniejące API DatabaseIdentity i dodano
inspekcję bez usuwania dotychczasowych funkcji. Host-level plik
`workspace_runtime/memory_rebuild_settings.json` pozostaje dozwolonym,
wąskim wyjątkiem; SYSTEM, MEMORY i dowiązania są nadal chronione.

Świeża walidacja: **111 PASS, 4 SKIPPED** dla konfiguracji, ustawień pamięci,
resolverów, operator paths, gateway recall/trust i runtime install. Dodatkowe
regresje gateway-to-real-SQLite, starego API identity i workspace settings:
**3 PASS**. Katalog kontraktów zsynchronizowany przez generator, `--check` PASS.
Wyniki te nie zastępują pełnego pytest, Pyright, package-smoke ani CI.

Stan operatora Test Studio, Pack i Version znajduje się poza SYSTEM.
Domyślny root to `~/.jazn/tools`, override `JAZN_OPERATOR_STATE_ROOT`.
Recenzje Test Studio oraz konfiguracja Version są rozdzielone hashem rootu.
Stare konfiguracje i kopie pozostają tylko źródłem odczytu; nie przenosimy ich.
Pytest runner wyłącza bytecode i kieruje własny cache poza SYSTEM.
Dowolny kod uruchamianych testów nadal wymaga własnej izolacji zapisów.

Dalsze wymagane kroki P0: pełne kontrole i diagnoza świeżych błędów,
kanoniczna synchronizacja wydania, PR i końcowy CI dla HEAD; następnie P1–P3.

Odczytać Git status/branch/HEAD, ten rejestr i rzeczywisty stan PR/CI. Nie
restartować aktywnego joba wyłącznie z powodu utraty obserwacji. Nowe testy
dołączyć przez kanoniczny sync_contract_catalog przed release_metadata_sync.
Istniejący test przed zmianą zarchiwizować bajt w bajt. Nie commitować
lokalnych logów, baz, venv, ZIP ani prywatnych danych.
