# Jaźń - Studio Testów

`Jaźń - Studio Testów` jest operatorską aplikacją do uruchamiania aktywnego zestawu pytest, obserwacji postępu, przeglądu wyników oraz kontroli celu i aktualności kontraktów testowych.

## Interfejsy

Ten sam rdzeń aplikacji udostępnia trzy kanoniczne tryby:

- `text` — prosty interaktywny terminal, użyteczny także przez SSH i przy ograniczonym terminalu;
- `tui` — pełnoekranowy dashboard terminalowy oparty na `prompt_toolkit` z nawigacją klawiaturą;
- `window` — okno Windows/Tk z zakładkami, tabelami, paskiem postępu i panelem diagnostycznym.

Historyczna nazwa `studio` pozostaje aliasem dla `window`.

```powershell
py -X utf8 .\tools\jazn_tests_studio.py --ui text
py -X utf8 .\tools\jazn_tests_studio.py --ui tui
py -X utf8 .\tools\jazn_tests_studio.py --ui window
```

Bez `--ui` używana jest lokalna konfiguracja operatora. Na Windows domyślnym trybem pierwszego uruchomienia jest `window`, na innych systemach `tui`.

## Struktura

- `app.py` — parser, lifecycle i dispatch interfejsów;
- `core.py` — katalog kontraktów, cache, recenzje i audyt;
- `runner.py` — nieblokujący subprocess pytest i strukturalne zdarzenia postępu;
- `ui_text.py`, `ui_tui.py`, `ui_window.py` — oddzielne widoki nad tym samym rdzeniem;
- `progress_plugin.py` — plugin pytest emitujący zdarzenia `collection/start/result/session_finish`;
- `test_contracts.json` — generowany katalog aktywnych kontraktów testowych;
- `settings.json` — polityka źródłowa Studia;
- `reviews.json`, `local_settings.json`, `runtime/` — stan poza SYSTEM:
  `~/.jazn/tools/jazn-tests-studio/<system-id>/`. Root można wskazać przez
  `JAZN_OPERATOR_STATE_ROOT`; walidator odrzuca kolizję z SYSTEM/MEMORY/runtime.
  Poprzednie pliki w katalogu narzędzia pozostają fallbackiem tylko do odczytu.

Każdy interfejs ma ekran główny i dostęp do ustawień. TUI oraz GUI mają oddzielny widok diagnostyczny; interfejs tekstowy udostępnia polecenia `settings` i `diagnostics`.

## Diagnostyka i przerwanie

Długie uruchomienia pytest pracują poza główną pętlą UI. `Ctrl+C` kończy aplikację kodem `130` bez tracebacku; aktywny subprocess testów jest najpierw zatrzymywany. Gdy diagnostyka jest włączona, zdarzenia aplikacji są zapisywane jako JSONL w `runtime/jazn-tests-studio.jsonl`.

Katalog JSON jest parsowany raz na zmianę pliku (cache kluczowany `mtime + size`), dlatego renderowanie listy testów nie wykonuje ponownie pełnego `json.loads()` dla każdego wiersza.

## P1: historia i eksport wyników (Studio Testów 1.4.0)

Każdy zakończony przebieg pytest zapisuje wyłącznie podsumowanie do `run_history.json` w izolowanym stanie operatora (`~/.jazn/tools/jazn-tests-studio/<system-id>/`). Dziennik jest ograniczony do 100 wpisów i nie zawiera stdout, parametrów poleceń, identyfikatorów testów, promptów, ścieżek ani treści MEMORY. Przekroczenie limitu, zły JSON lub niedozwolona lokalizacja kończy się diagnozą fail-closed, nigdy czyszczeniem historii bez wiedzy operatora. Testy i zapisy historii mają oddzielne statusy sukcesu.

```powershell
py -X utf8 .\tools\jazn_tests_studio.py history --limit 20
py -X utf8 .\tools\jazn_tests_studio.py history-export --output "D:\Raporty\jazn-tests-history.json"
```

Eksport tworzy wyłącznie nowy plik JSON pod jawną, absolutną ścieżką. Nadpisanie istniejącego pliku i zapis w SYSTEM/MEMORY/runtime są zabronione. Okienko Studio ma oddzielną zakładkę Historia z ręcznym odświeżeniem. Brak historii nie jest dowodem, że testy nigdy się nie odbyły.


## Zbiorczy przebieg i rzeczywisty odbiór JSS

W natywnym JSS otwórz **Katalog testów** i użyj
**Uruchom WSZYSTKIE aktywne testy (pytest)**. Akcja wymaga potwierdzenia,
wybiera Python ustawiony w JSS, wykorzystuje istniejący runner Test Studio,
wykonuje pełną aktywną kolekcję poza wątkiem Qt, pokazuje licznik,
pozwala anulować własny proces i zapisuje trwałe dowody:

- operator-only `batch-evidence/run-<uuid>/junit.xml`;
- rejestrowany `JAZN_TEST_EVIDENCE_DIR` z manifestem wszystkich scenariuszy,
  osobnymi TXT/JSON i integralnością weryfikowaną przez istniejący plugin;
- osobny, redagowany wpis w historii Test Studio.

Nie są uruchamiane dodatkowe daemony, nie jest modyfikowana MEMORY,
nie ma automatycznej instalacji bibliotek. Ścieżkę raportu pokazuje JSS.
Wynik `pytest=PASS` nie oznacza `full_gate=PASS`, także gdy są pominięcia.
Wszystkie nieuruchomione testy i odbiory pozostają `NOT_RUN`.

Przycisk **Odbiór zbiorczy TPA** przenosi do istniejącego
planu **Uruchom plan automatyczny**. Domyślnie TPA wykonuje 22 izolowane
regresje. Żywe testy daemona i Ollamy są osobnym, jawnym opt-in, wymagają
lokalnego modelu i odrębnych dowodów; fizyczny Windows/EXE/DPI i ręczne
odbieranie studiów pozostają kontrolami operatorskimi. Akcja nie
nadaje automatycznie PASS pełnym odbiorom.

Jeżeli operator korzysta z terminala, nadal dostępne są:
```bash
python -X utf8 tools/jazn_tests_studio.py run-all --timeout 7200
python -X utf8 tools/jazn_tests_studio.py audit
```

## Zamknięcie nieaktualnego testu: audyt → archiwum → ponowne CI

Status `obsolete` jest tylko oceną operatora. Domyślny `run-all`
**nadal wykonuje takie testy**, dopóki nie zostaną formalnie wycofane
z aktywnego drzewa. Nie wolno wyciszać ich przez automatyczny skip,
deselekcję albo xfail tylko po to, żeby CI było zielone.

Jedynie **cały moduł testowy** może być zarchiwizowany przez
`retire-file`; pojedynczego testu ze wspólnego pliku nie usuwa się
automatycznie. Dla każdego testu z wybranego pliku operator musi
jawnie oznaczyć `obsolete` i wskazać istniejący, aktualny test
zastępczy **w innym pliku**:

```bash
python -X utf8 tools/jazn_tests_studio.py review \
  'tests/test_old.py::test_case' --status obsolete \
  --replacement-nodeid 'tests/test_new.py::test_equivalent' \
  --note 'Przegląd kontraktu i dowodu zachowania wymagania'
python -X utf8 tools/jazn_tests_studio.py retirement-preview \
  --file tests/test_old.py
```

Podgląd nie zmienia plików i zwraca `source_sha256`,
`BLOCKED` lub `REVIEW_READY`, listę zamienników i jawną
informację `full_release_gate=NOT_VERIFIED`. JSS pokazuje taki
podgląd również przy zaznaczonym teście.

Dopiero po rzeczywistym zielonym CI dla **dokładnego SHA**, na
czystej gałęzi innej niż master/main i po przeglądzie zastępczych
kontraktów operator może jawnie wykonać:

```bash
python -X utf8 tools/jazn_tests_studio.py retire-file \
  --file tests/test_old.py \
  --expected-sha256 <HASH_Z_PREVIEW> \
  --expected-head <ZWERYFIKOWANY_HEAD_SHA> \
  --confirm ARCHIWIZUJ --apply
```

Narzędzie sprawdza w publicznym GitHub bieżące check-runs z SHA,
wymaga sukcesu wszystkich zwróconych kontroli i obecności
podstawowych bramek wydaniowych Windows/Linux. Nie może obejść
brakującego CI albo nieaktualnego SHA. Archiwum zachowuje **identyczne
bajty oryginału** i metadane provenance w `tests/archive/` przed
usunięciem aktywnego pliku. Nie zapisuje tam prywatnej MEMORY.

Po takiej zmianie **konieczne** jest ponowne kanoniczne wygenerowanie
katalogu Test Studio, synchronizacja release metadata oraz nowe CI
na SHA **po archiwizacji**. Bieżące zielone CI jest wyłącznie
warunkiem rozpoczęcia operacji, nie akceptacją nowego commita.
Skrypt nie zatwierdza za człowieka 22 odbiorów TPA, nie wykonuje merge
i nie usuwa historycznych dowodów.
