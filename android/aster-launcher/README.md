# Aster Launcher

Oryginalny launcher dla Androida rozwijany niezależnie od Smart Launchera.

## Wersja 0.1.0

Pierwsza instalowalna wersja zawiera:

- deklarację systemowej roli ekranu głównego (`HOME`),
- przycisk wyboru Aster Launcher jako domyślnego launchera,
- odczyt zainstalowanych aplikacji,
- przewijaną siatkę ikon,
- wyszukiwanie po nazwie i identyfikatorze pakietu,
- uruchamianie aplikacji,
- przejście do informacji o aplikacji po przytrzymaniu,
- zegar i datę,
- półprzezroczysty interfejs nad tapetą,
- obsługę Androida 8.0 i nowszego.

## Kompilacja

```bash
gradle :app:assembleDebug
```

Plik wynikowy:

```text
app/build/outputs/apk/debug/app-debug.apk
```

GitHub Actions automatycznie buduje i udostępnia artefakt `Aster-Launcher-APK` po zmianie projektu na gałęzi `aster-launcher-v0.1`.

## Plan rozwoju

Kolejne moduły obejmą trwały układ pulpitu, dock, foldery, kategorie, widżety, gesty, paczki ikon, ukryte aplikacje, kopie zapasowe i rozbudowane motywy.
