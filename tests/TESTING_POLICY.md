# Polityka testów Jaźni

## Tożsamość testu

Test nazywamy według trwałego przeznaczenia, nie według numeru wydania systemu. Nowa wersja Jaźni nie tworzy nowej nazwy tego samego testu. Numer wersji może pozostać wyłącznie wtedy, gdy jest częścią badanego formatu, schematu, protokołu albo ścieżki migracji.

## Aktualizacja

Przed zmianą aktywnych testów tworzony jest byte-exact snapshot w `tests/archive/branches/<wersja>__<commit>/` z `MANIFEST.json`. Stary test nie pozostaje w aktywnym drzewie tylko po to, by zachować historię — historię zapewniają Git i snapshot.

## Kontrakt

Każda aktywna definicja testowa ma rekord w `tools/jazn_tests_studio/test_contracts.json`: cel, oczekiwane zachowanie, kategorię, tagi, liczbę asercji i powiązane moduły. Status `current` oznacza technicznie aktywny kontrakt; semantyczna recenzja może oznaczyć go jako `review_required`, `obsolete` albo `incompatible`.

## Zasady

- test ma potwierdzać obserwowalne zachowanie lub kontrakt, nie numer bieżącego release;
- zależności opcjonalne powodują kontrolowany skip, gdy capability nie jest zainstalowana;
- kontrole repozytorium/formatowania należą do CI lub kategorii `repository`, a nie do runtime produktu;
- archiwum nie jest zbierane przez zwykły `pytest`;
- poprawa istniejącego celu aktualizuje istniejący test pod stałą nazwą.
