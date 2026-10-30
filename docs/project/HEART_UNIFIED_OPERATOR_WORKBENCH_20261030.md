# Jaźń — Serce Systemu: audyt GUI i wspólny panel operatorski

Data: 2026-10-30. Punkt wyjścia: integration/tpa-heart-studio-20261029 / ff6d5927. To oddzielna gałąź WIP i nie oznacza zakończenia P1–P5 ani pełnego TPA.

## Przyczyna chaosu interfejsu

W dotychczasowym JSS występują dwa konkurencyjne panele dolne: stary QTabWidget z logami w Window i oddzielny QDockWidget narzędzi operatora. Ich widoczność jest przełączana wzajemnie. W dodatku trzy konsole zadań zajmowały jedną kolumnę, sześć usług przewijało się wewnątrz zbyt niskiej tabeli, a surowy JSON zajmował miejsce pod przyciskami usług. Oddzielnie uruchamiane klasyczne Studia nie korzystają z pełnej palety i komponentów Qt.

## Własność funkcji — bez dublowania backendu

| Działanie | Moduł odpowiedzialny | Prezentacja |
| --- | --- | --- |
| Nawigacja, menu, status | Window, WorkbenchShell | jeden shell jak IDE |
| Pierwsze uruchomienie | SetupWizard | kreator z jawną zgodą |
| Usługi i procesy | Controller, Window | tabela sześciu usług; techniczne w dolnym panelu |
| Czat Ollama | Controller i kanoniczny chat bridge | osobny widok rozmowy, nie konsola |
| TPA | TPAPanel, TPARunner, istniejący report store | tabela scenariuszy; zachowana historia i dowody |
| Problemy, logi, historia, techniczne | OperatorWorkspace | jeden współdzielony dolny dock |
| Zadania | TaskConsole | osobne karty zadań; to nie jest PTY |
| Dwanaście Studiów | STUDIOS, własne kontrolery | natywne formularze i zwarty selektor klasycznych okien |
| Wygląd i adaptacja | VisualSystem, workbench_theme | sześć motywów, wspólny fokus, skalowanie |
| Układ | workspace_layout | ograniczony JSON v3, wsteczna zgodność v1/v2 |

## Wykonane na nowej gałęzi

- W produkcyjnym widoku logi i Ctrl+J prowadzą do jednego dolnego docka. Dawne zakładki istnieją jeszcze jako powierzchnia kompatybilności izolowanych testów Qt.
- Dolny dock ma: Problemy, Output/Logi, Konsole zadań, Historia, Techniczne.
- Historia odczytuje raporty z istniejącego magazynu TPA; nie przepisuje dowodów ani nie nadaje pełnych bramek na podstawie regresji.
- Trzy zadaniowe konsole są przełączane kartami; każda ma pełną wysokość obszaru.
- Dane techniczne są prezentowane na żądanie w dolnym panelu, a tabela usług ma więcej miejsca na sześć wierszy.
- Dwanaście stale rozwiniętych przycisków klasycznych Studiów zastąpił opisany selektor. Kanoniczne wywołania pozostały.
- Układ zapamiętuje aktywną dolną zakładkę z walidacją schematu i migracją v1/v2.
- Dodano testy izolowane GUI i kontraktu układu. Nie zostały jeszcze uruchomione na tej gałęzi.

## Pozostałe nieukończone prace

P2: rzeczywisty wbudowany terminal ConPTY na Windows i PTY na Linux, strumieniowanie UTF-8, ANSI/VT, interaktywne stdin, obsługa Ctrl+C, resize, zakładki sesji i własny bezpieczny cleanup. QProcess z rurami nie wystarcza do udawania pełnego terminala. Obecny przycisk otwiera prawdziwą zewnętrzną konsolę Windows.

P3: pełne workflow usług, ownership, start/status, supervisor, Ollama, MCP i błędy. Nigdy nie utożsamiać PID z gotowością rozmowy ani nie przejmować cudzej usługi.

P4: natywna migracja funkcji wszystkich 12 Studiów, w tym Test, Version Rebuild, Import/Export, syntetyczne Restore MEMORY i stany transakcji. Klasyczne okno nie jest dowodem parytetu.

P5: dwa rzeczywiste, zaakceptowane turny Ollama, resume/reconnect, sesja po restarcie, offline EXE, AV, TPA full_gate i końcowy odbiór Windows/Linux.

P1: ekran 860×580, 1240×840 i 1920×1080; każdy z sześciu motywów, klawiatura, focus, WCAG, tooltips, fizyczne DPI 100/150/200%; wszystkie widoki, kreatory i dialogi. Dokładnie oddzielić raport z renderowania od fizycznego odbioru.

## Granice i gate wydania

Nie zmieniać master, prywatnej MEMORY, aktywnego daemona ani sekretów. Przed merge wykonać testy Qt w Windows/Linux, prawdziwą walidację PTY/ConPTY, regresje TPA oraz kanoniczną synchronizację manifestu i provenance, strict audit wersji i końcowe CI. Ten host nie udostępnił działającego executora; nie deklarować PASS dla niewykonanych testów. PR musi pozostać Draft. Kanoniczne metadane wolno zapisać tylko uruchomieniem latka_jazn.tools.release_metadata_sync; bez ręcznych zmian JSON.

## Dokumentacja źródłowa

- Qt QMainWindow/QDockWidget: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html
- Qt QProcess: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html
- Microsoft ConPTY: https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session

## Decyzja operatorska: dwa motywy i stabilny panel dolny

Na wyraźną prośbę operatora aktualna powłoka JSS udostępnia tylko
**Ciemny** i **Jasny**. Domyślny jest Ciemny. Są to neutralne, kontrastowe
warianty przeznaczone dla wszystkich natywnych stron, formularzy i dialogów
Qt. Historyczne `violet-night`, `purple`, `system` i `custom` mogą nadal
zostać odczytane przez kontrakt Settings, aby nie blokować starych profili.
Ich efektywna prezentacja jest Ciemna; oryginalna konfiguracja nie jest
przepisywana podczas odczytu. Dopiero jawny zapis ustawia motyw `dark` lub
`light`. Zależne od starej palety archiwalne okna Tk nie zostały
automatycznie uznane za zgodne z dwoma motywami.

Jedyny dock narzędzi zachowuje wybraną zakładkę oraz kontrolowaną wysokość
180–3000 pikseli logicznych. Przy przełączaniu zakładek nie nadpisuje
ręcznej zmiany wielkości. Zachowana jest migracja układu v1/v2 do
obecnego v3 bez odczytu nieufanych danych binarnych Qt.

Nowy test `tests/test_heart_light_dark_operator_qt.py` obejmuje wybór
dwóch motywów, zgodność historycznych nazw, kontrast tekstu oraz ochronę
wymiarów panelu. Jest to **deklaracja zakresu testu**, nie dowód jego
ukończenia na Windows/Linux. Końcowe CI i fizyczny odbiór GUI są wymagane.

### Macierz odbioru UI do wykonania

| Widok | Ciemny/Jasny | Minimalny ekran | Klawiatura/DPI | Funkcje |
| --- | --- | --- | --- | --- |
| Pierwsze uruchomienie A/B/C | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Pulpit, Usługi, Czat lokalny | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Diagnostyka, Katalog testów, TPA | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Konfiguracja Qt, Wersje Qt | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| MEMORY i pozostałe 12 Studiów | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Problemy, Logi, Historia, Techniczne | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Konsole zadań i prawdziwy PTY | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Wszystkie dialogi i menu | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

Wszystkie komórki odbioru pozostają NOT_RUN do przedstawienia
wyników z Windows i Linux. Konsole zadań to wciąż zadania operatora,
nie ConPTY; pełny terminal i parytet klasycznych Studiów są osobnymi
nieukończonymi etapami.
