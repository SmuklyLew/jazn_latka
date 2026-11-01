# JSS Workbench — układ profesjonalny i odbiór TPA

## Źródła projektowe

- VS Code: [User Interface](https://code.visualstudio.com/docs/editing/getting-started/userinterface) — Activity Bar, Primary Side Bar, Editor, Panel, Status Bar
- VS Code: [Modernizing the VS Code UI](https://code.visualstudio.com/blogs/2026/10/15/modern-ui) — wspólne tokeny, hierarchia, czytelność i konfiguracja obszarów
- Qt: [QMainWindow](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html) — docki, stan układu, ostrzeżenia dotyczące niezaufanego restoreState

## Aktualna realizacja tej zmiany

- Wąski pasek aktywności z własnymi ikonami wektorowymi Qt (bez zależności od zewnętrznych fontów ani sieci)
- Oddzielne kontenery nawigacji: Pulpit, Czat, Usługi, MEMORY, Testy i TPA, Studia, Developer, Ustawienia
- Stałe indeksy istniejących ekranów Qt, zgodność komend, palety poleceń i historii kart
- Na małym oknie pasek aktywności pozostaje widoczny, a boczny panel może się zwinąć
- Centralny obszar roboczy zachowuje własne widoki, dokowany operator pozostaje jednym właścicielem terminala/logów
- TPA: jawny przycisk pełnego odbioru, przewijany kreator, miejsca źródła, kopii, interpretera i raportów
- PASS regresji nigdy nie nadaje pełnego PASS; schemat dowodów, wymagania `LIVE_CASES` i kontrola źródła pozostają bez zmian

## Ograniczenia / prace do odbioru

To nie jest jeszcze wizualna kopia VS Code. Zrzuty przekazane przez użytkownika są referencją, nie zasobem już wbudowanym do repozytorium: **oryginalne logo JSS nie zostało jeszcze dodane do pakietu**. Czat nadal używa sprawdzalnego, prostego widoku rozmowy, a nie odrębnej architektury wielosesyjnej. Nie dodano fikcyjnych funkcji (np. bibliotek konwersacji bez backendu).

Weryfikacja przed wydaniem: testy Qt na Windows/Linux w 860×580 i 1240×840; kilka motywów; Activity Bar, skróty klawiszowe, TPA z przewijaniem i załączaniem dowodów, brak dodatkowego daemona; screenshoty realnego GUI, kompletna macierz checków. Scenariusze wymagające człowieka, prawdziwej Ollamy i operacyjnego Windows nie są automatycznie zaliczane przez regresję.
