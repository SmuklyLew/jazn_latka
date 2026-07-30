# Jaźń Memory Rebuild Studio

`Jaźń Memory Rebuild Studio` jest projektową aplikacją operatorską nad kanonicznym silnikiem `latka_jazn.tools.memory_restore`. Nie zastępuje silnika, nie zmienia surowych źródeł i nie promuje automatycznie pamięci do L2 ani L3.

## Uruchomienie

Najprościej:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py
```

Tryb tekstowy:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py --text-ui
```

Konfiguracje projektów są domyślnie zapisywane poza repozytorium:

```text
%USERPROFILE%\.jazn\memory_rebuild_projects\
```

Inny prywatny katalog:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py `
  --project-root D:\PRIVATE\memory_rebuild_projects
```

## Najważniejsza zasada

Bazy z Testów 01–04 pozostają niezmiennymi baseline’ami. Aplikacja otwiera je w trybie tylko do odczytu i wykorzystuje do:

- `quick_check` albo pełnego `integrity_check`;
- `foreign_key_check`;
- odczytu liczników znanych tabel;
- obliczenia SHA-256;
- porównania spadków, przyrostów i brakujących baz.

Usunięcie baseline’u z projektu usuwa tylko wpis konfiguracji. Nie usuwa baz z dysku.

## Projekty odbudowy

Projekt zapisuje:

- nazwę i prywatny identyfikator;
- katalog docelowy;
- tryb `developer` albo `system`;
- źródła i ich kolejność;
- dowolną liczbę baseline’ów;
- ustawienia walidacji i bezpieczeństwa;
- ostatni plan i wynik;
- notatki operatora;
- rewizję konfiguracji.

Każdy wcześniejszy zapis projektu jest archiwizowany pod `.history/<project-id>/` przed zastąpieniem pliku bieżącego.

## Rejestr źródeł

Każdy plik może otrzymać:

```text
role
source_family
truth_domain
pipeline
enabled
approved
notes
sha256
status
warnings
metadata
```

Obsługiwane role:

```text
chatgpt_export
chatgpt_html_export
journal
approved_l0
layered_memory
runtime_event_ledger
sqlite_snapshot
reference_document
visual_asset
unknown
```

Pipeline’y:

```text
memory_rebuild
html_control
catalog_only
sqlite_baseline
excluded
```

Granice prawdy:

```text
conversation_event
source_recorded
user_confirmed
assistant_claim
runtime_claim
dream
imagination
book_scene
roleplay
symbolic
technical
unknown
```

Sama klasyfikacja nie zmienia treści źródłowej i nie stanowi zatwierdzenia pamięci.

## Inspekcja ZIP

Aplikacja wykrywa:

- `conversations.json` i ponumerowane części rozmów;
- pliki HTML i zasoby graficzne;
- niebezpieczne ścieżki i ścieżki bezwzględne;
- symlinki;
- powtórzone wpisy i kolizje wielkości liter;
- profil paczki z wewnętrznych plików `.package.json`;
- opcjonalnie pełny test CRC.

SHA-256 jest domyślnie obliczany. Pełny CRC dużych archiwów jest domyślnie wyłączony i wymaga jawnego włączenia.

## HTML rozmów

HTML jest rejestrowany jako `chatgpt_html_export` i domyślnie trafia do `html_control`. Nie zastępuje kanonicznego drzewa rozmów z JSON. Służy do kontroli, mapowania zasobów i porównania widocznej ścieżki rozmowy.

## Manifest projektu i manifest Testu 04

Aplikacja eksportuje:

1. pełny manifest projektu, zawierający wszystkie role i metadane;
2. zgodny manifest `jazn_memory_sqlite_test04_sources/v1`.

Obecny Test 04 przyjmuje role `chatgpt_export`, `journal` i `approved_l0`. HTML jest mapowany do `chatgpt_export` z pipeline’em `html_only_review`. Pozostałe źródła są jawnie zapisane w `app_metadata.excluded_sources` z powodem wykluczenia.

`operator_attestation` pozostaje domyślnie `false`. Aplikacja nie składa oświadczeń za użytkownika.

## Preflight

Preflight blokuje plan lub zapis, gdy między innymi:

- brakuje katalogu docelowego;
- aktywne źródło nie istnieje;
- inspekcja wykryła blokujące zagrożenie ZIP;
- nie ma żadnego źródła `memory_rebuild`;
- cel developerski znajduje się wewnątrz repozytorium.

Ostrzeżenia obejmują dziennik umieszczony przed eksportem rozmów i HTML skierowany do niewłaściwego pipeline’u.

## CLI bez UI

Lista projektów:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py list-projects
```

Utworzenie projektu:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py `
  --project-root D:\PRIVATE\memory_rebuild_projects `
  create-project `
  --name "Pełna pamięć Łatki 2025-2026" `
  --target-root D:\PRIVATE\jazn_memory_test_05 `
  --source-directory D:\Dokumenty\.ProjektGPT\.archiwum\.down-zip
```

Dodanie źródła:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py `
  --project-root D:\PRIVATE\memory_rebuild_projects `
  --project <project-id> `
  add-source D:\PRIVATE\journal_from_sqlite.jsonl `
  --approved
```

Dodanie baseline’u:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py `
  --project-root D:\PRIVATE\memory_rebuild_projects `
  --project <project-id> `
  add-baseline D:\.AI\work\jazn_memory_test_03 `
  --label "Test 03"
```

Preflight i plan:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py `
  --project-root D:\PRIVATE\memory_rebuild_projects `
  --project <project-id> preflight

py -X utf8 .\tools\rebuild_memory_app.py `
  --project-root D:\PRIVATE\memory_rebuild_projects `
  --project <project-id> plan
```

Odbudowa developerska wymaga dokładnego tokenu:

```powershell
py -X utf8 .\tools\rebuild_memory_app.py `
  --project-root D:\PRIVATE\memory_rebuild_projects `
  --project <project-id> run `
  --confirm RESTORE
```

Tryb systemowy zachowuje token związany z pełną ścieżką celu:

```text
SYSTEM_RESTORE:<bezwzględna ścieżka>
```

## Zależności UI

Interfejs kursorowy używa `prompt_toolkit`. Silnik i tryb tekstowy pozostają dostępne bez tej biblioteki.

```powershell
py -m pip install -e ".[memory-rebuild-ui]"
```

## Bezpieczeństwo

- aplikacja nie zapisuje `memory/`, SQLite ani prywatnych manifestów do Git;
- surowe L0 pozostaje bez zmian;
- edytowane są wyłącznie projekty, metadane i decyzje operatorskie;
- automatyczna akceptacja doświadczeń jest stale wyłączona;
- automatyczna promocja L2 i L3 jest stale wyłączona;
- publikacja do runtime nadal wymaga oddzielnego procesu Verified Memory Restore;
- obecność pamięci, wake-state lub SQLite nie dowodzi aktywnej Jaźni.
