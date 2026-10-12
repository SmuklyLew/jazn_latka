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
