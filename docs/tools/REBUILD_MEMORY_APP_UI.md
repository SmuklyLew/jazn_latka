# Memory Rebuild Studio — uproszczony interfejs użytkownika

## Cel

Interfejs prowadzi operatora krok po kroku przez przygotowanie odbudowy pamięci. Surowe źródła oraz bazy testowe pozostają niezmienne. Edytowane są wyłącznie wpisy projektu, role, kolejność, domeny prawdy, sposób użycia i notatki operatora.

## Uruchomienie

```powershell
py -X utf8 .\tools\rebuild_memory_app.py
```

Domyślny katalog prywatnych projektów można ustawić zmienną:

```powershell
[Environment]::SetEnvironmentVariable(
    "JAZN_MEMORY_REBUILD_PROJECTS",
    "D:\PRIVATE\memory_rebuild_projects",
    "User"
)
```

## Główna kolejność pracy

1. **Źródła pamięci** — dodaj pliki lub przeskanuj folder.
2. **Bazy testowe** — dodaj Testy 01–04 jako zestawy tylko do odczytu.
3. **Ustawienia projektu** — sprawdź katalog docelowy i główny folder źródeł.
4. **Sprawdź gotowość** — zobacz komunikaty opisowe zamiast surowych kodów.
5. **Plan bez zapisu** — wykonaj symulację bez modyfikowania baz docelowych.
6. **Kontrolowana odbudowa** — wymaga jawnego tokenu.
7. **Porównanie** — zestaw wynik z zachowanymi bazami testowymi.

## Folder źródeł

Dla bieżącej odbudowy zalecany folder to:

```text
D:\.AI\work\memory_to_restore
```

Opcja **Przeskanuj folder źródeł**:

- otwiera systemowe okno wyboru folderu;
- pozwala skanować podfoldery;
- uwzględnia foldery zaczynające się kropką, w tym `.BardzoStareCos`;
- pokazuje pogrupowaną listę znalezionych plików;
- pozwala dodać wszystkie albo wybrać konkretne pliki;
- nie dodaje samego folderu jako pliku źródłowego;
- pomija nieobsługiwane sidecary, np. `.sha256`.

Obsługiwane są między innymi ZIP, JSON, JSONL, NDJSON, HTML, dokumenty pomocnicze, grafiki i migawki SQLite. Dopiero klasyfikacja źródła decyduje, czy trafi ono do `memory_rebuild`, `html_control`, `catalog_only`, `sqlite_baseline` albo `excluded`.

## Lista źródeł

Każdy wpis pokazuje:

- kolejność;
- stan włączony/wyłączony;
- czy plik przeszedł podstawową kontrolę;
- czytelną rolę, np. „Eksport rozmów ChatGPT” albo „Dziennik”;
- nazwę pliku.

Po otwarciu wpisu można:

- zobaczyć podgląd opisowy;
- zobaczyć pełny JSON techniczny;
- odświeżyć SHA-256 i rozpoznanie;
- zmienić plik lub ścieżkę;
- zmienić rolę, domenę prawdy i pipeline;
- włączyć albo wyłączyć wpis;
- zatwierdzić albo cofnąć zatwierdzenie;
- dodać notatkę operatora;
- zmienić kolejność;
- usunąć wpis z projektu.

Usunięcie wpisu nie usuwa pliku z dysku.

## Lista baz testowych

Bazy Testów 01–04 są otwierane tylko do odczytu. Lista pozwala:

- dodać pojedynczy folder testu;
- wyszukać wiele zestawów baz pod wskazanym folderem;
- zobaczyć liczbę dostępnych baz;
- wykonać `quick_check` albo pełny `integrity_check`;
- zmienić nazwę wyświetlaną i ścieżkę wpisu;
- włączyć lub wyłączyć zestaw w porównaniach;
- usunąć wyłącznie wpis projektu.

Pliki SQLite nie są usuwane ani edytowane.

## Komunikaty gotowości

Surowe kody pozostają w widoku **Szczegóły techniczne**. Widok podstawowy wyjaśnia po polsku:

- czego brakuje;
- który plik nie istnieje;
- czy folder został błędnie dodany jako plik;
- czy nie ma źródła przeznaczonego do odbudowy;
- jaki jest następny krok.

Przykład naprawy błędu `source_not_file`:

1. usuń błędny wpis folderu z listy źródeł;
2. wybierz **Przeskanuj folder źródeł**;
3. wskaż `D:\.AI\work\memory_to_restore`;
4. włącz skanowanie podfolderów, aby objąć `.BardzoStareCos`;
5. przejrzyj znalezione pliki i dodaj wybrane wpisy.

## Granice bezpieczeństwa

- brak automatycznej akceptacji doświadczeń;
- brak automatycznej promocji L2 i L3;
- brak edycji surowego L0;
- brak zapisu do baseline'ów;
- brak usuwania źródeł i baz z dysku przez operacje listy;
- zapis odbudowy wymaga jawnego tokenu potwierdzenia;
- pełne dane techniczne pozostają dostępne, ale nie zasłaniają podstawowego interfejsu.
