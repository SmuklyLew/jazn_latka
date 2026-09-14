# Jaźń Studio Pamięci .76 — checkpoint batch reconstruction

Status: IN_PROGRESS. Przerwa na wyraźną prośbę operatora; to nie jest końcowa akceptacja wydania.

## Stan i pochodzenie

- Aktywna linia: `fix/v16.3.25.5.75-jazn-studio-pamieci-master73-convergence-next-step`.
- Zweryfikowany bieżący master: `9d38a294c0479078e75b6385c8d46561c5d055c7`.
- Konwergencja: `8d8f7169527be99a71ca575c7a306e334bfb69ef`; metadane: `e1957f3b85c827a00918d6eba703893c88219e31`.
- Niezmieniony syntetyczny RED: `3b4ade4a`, następnie checkpoint `82d4eb2b78c471a4b9938876ccb16c3147db6d34`.
- Bezpośredni punkt przywracania przed implementacją: `7b82e291` (wyłącznie automatyczna aktualizacja metadanych).
- Nowa wersja silnika: `16.3.25.5.76-jazn-studio-pamieci-deterministic-batch`. Przed zmianą sprawdzono branche, tagi, aktualny master i listę wydań; .76 była wolna.
- Zmiany hosta .74.1.001 pochodzą z mastera. Nie importowano ponownie historycznego brancha hosta.

## Przyczyna i implementacja

Sekwencyjny import wyznaczał rewizję względem aktualnego rekordu. Kolejność eksportów zmieniała bieżącą treść i identyfikatory; ponowne napotkanie historycznego wariantu mogło tworzyć dodatkową rewizję.

Nowy `BatchPlan` przygotowuje rekordy wszystkich źródeł w tymczasowym SQLite przed zapisem bazy docelowej. Każdy adapter przygotowywany jest raz na wejście, a iterator rekordów źródła konsumowany raz. Warianty są grupowane według logical_key/content_sha256, porządkowane według wiarygodnego czasu UTC i hasha treści; reprezentant i occurrence links mają stabilne rozstrzyganie według tożsamości źródła. Decyzja jest zapisana w provenance. Nieznane i niejednoznaczne lokalne czasy nie ustanawiają chronologii.

`import_sources(mode="batch")` wymaga pustej bazy L0. Native projections wykonywane są w porządku semantycznych tożsamości źródeł, a wspólny L0 zapisuje cały plan w jednej transakcji. Nazwy źródeł w semantycznym L0 są adresami treści; oryginalne lokalne nazwy i ścieżki pozostają w `source_locators` raportu importu.

`import_source()` i `import_sources(mode="incremental")` zachowują późniejsze, świadome aktualizacje. Domyślny `mode="auto"` zachowuje kompatybilność: pusta baza wybiera batch, zasilona baza — incremental. Studio wybiera tryb jawnie na podstawie create/update; świeże budowy protokołu jawnie wybierają batch. Nie zmieniono walidatora Test03 ani porównania normal/reverse. Automatyczne L2/L3/activation pozostają wyłączone.

## Aktualne publiczne wyniki

- RED przed zmianą: 2 FAIL (normal/reverse i przeniesienie/nazwy plików), 1 PASS (kontrola incremental).
- Ten sam niezmieniony test po zmianie: 3 PASS.
- Pakiet ukierunkowany (regresja, modular, v24 unified, v4 protocol engine, Studio, FTS): 48 PASS.
- Nowe kontrakty: 4 PASS; obejmują wszystkie sześć permutacji trzech źródeł z przeciwną chronologią rekordów, powtórzony wariant historyczny, deterministyczny remis/provenance, liczbę przygotowań adaptera, brak bazy po błędzie przygotowania i odmowę batch na zasilonej bazie.
- Pyright trzech plików silnika: PASS, 0 errors / 0 warnings.
- Kanoniczna synchronizacja katalogu Test Studio: PASS.

## Pozostała praca

1. Przegląd implementacji i dodatkowe scenariusze ChatGPT/journal/native projections, duże źródła, powtórzenia oraz przenoszenie źródeł. Sprawdzić trwałość informacji o lokalizatorach i odporność na zmianę źródła między przygotowaniem a native projection.
2. Naprawa konfiguracji oczekiwanego branch/ref w Python Test04 i PowerShell; obecny historyczny hardcode NIE JEST JESZCZE NAPRAWIONY. Przed zmianą istniejących testów zachować snapshoty byte-for-byte.
3. Nowy prywatny chain Test00 → Test01 → Test02 → Test03 → zamrożony benchmark 13 przypadków → Test04 → Final. NOT RUN dla nowego silnika. Historyczny prywatny Test03 FAIL pozostaje niezmienionym dowodem, a nie bieżącym wynikiem .76.
4. Pełne testy Memory Studio, host handoff/ingress, pełny aktywny pytest, pełny Pyright, compileall i obowiązujące release/governance checks. NOT RUN na całym finalnym drzewie.
5. Końcowy raport rzeczywistych wyników, kontrola CI, spójność metadanych i push finalnych checkpointów. Nie deklarować DONE na podstawie tego checkpointu.

Prywatne źródła, bazy, logi i benchmark pozostają poza Git. Nie aktywowano pamięci runtime. Nie zmieniono historycznych raportów ani oczekiwań regresji RED.
