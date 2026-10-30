# JSS — kontrakty ekranów, interakcji i odbioru

To dokument projektu UX. Opisuje **istniejące funkcje, wymagania docelowe i granice odbioru**, nie należy interpretować wszystkich punktów jako ukończonych funkcji aplikacji. Nie ma zgody na uruchamianie, zatrzymywanie ani modyfikowanie środowiska użytkownika podczas projektowania.

## 1. Matryca ekranów

| Ekran | Treść / interakcje | Istniejące źródło danych lub widok | Wymagany dalszy odbiór |
|---|---|---|---|
| Start / Pulpit | Logo, nawigacja, stan komponentów, szybkie akcje, ostatnia zakończona operacja | `Window._dashboard`, `status_summary` | Widok bez niezweryfikowanego sukcesu, responsywność |
| Usługi | Tabela Jaźń/Ollama/MCP lokalne/MCP HTTPS/Supervisor/MEMORY, akcja wybranej usługi | `Window._services`, `refresh_service_table`, `Controller` | Testy na prawdziwym Windows + ochrony właściciela procesu |
| Runtime | Wersja, kontrakty, identity procesu, endpoint, heartbeat, readiness | Publiczne statusy i `operator_workspace` | Brak automatycznego restartu, rozdział readiness/turn |
| Output | Logi, błędy, przewijanie, filtr, eksport po redakcji | `operator_workspace.py`, `Window.show_log` | Zero ujawnionych sekretów i prywatnej pamięci |
| Testy / TPA | Katalog, cele testów, 22 scenariusze TPA, stan wykonania, wyniki | `test_catalog_view.py`, `tpa_view.py`, `tpa_live.py` | Historia i manualny gate osobno od PASS syntetycznego |
| Pamięć | Techniczna dostępność i źródło, ograniczenia recall | `memory_view.py` | Bez odczytu prywatnych rekordów z interfejsu statusowego |
| Ustawienia | Kategorie, wyszukiwarka, ścieżki, motywy, walidacja, zapis | `Window._settings`, `core.Settings` | Wyróżnienie zapisane/niezapisane + trzy nowe style |
| Czat lokalny | Rozmowa po kanonicznej trasie, status sesji, rozłączenie | `chat.py`, `chat_protocol.py` | E2E dwóch tur z trwałym daemonem |
| Połączenia | Lokalny MCP, HTTPS, tunel, OAuth, narzędzia hosta | `Window._connections`, `probes.py` | E2E z prawidłowo uwierzytelnionym wdrożeniem |
| Developer | Git, diagnostyka, raport, komendy i dowody | `Window._developer`, `workbench_shell.py` | Brak prywatnego chain-of-thought i materiału niepublicznego |

## 2. Interakcje wspólne

1. Lewy pasek aktywności przełącza moduły; Explorer pokazuje strukturę nawigacji. Aktywna sekcja ma etykietę tekstową, nie tylko ikonę.
2. Centrum to aktualny moduł; zakładki pozwalają wracać do otwartych stron.
3. Dolny lub boczny panel diagnostyczny można otworzyć, przenieść, odpiąć i ukryć. Użytkownik zachowuje sterowanie układem.
4. Globalny wybór stylu ma trzy nowe opcje oraz sześć dawnych. Technical jest domyślny **tylko dla nowych profili**. Zapisany dawny wybór pozostaje niezmieniony.
5. Zmiana wyglądu nie może wpływać na owner/pid/status usług i nie powinna na nowo uruchamiać procesów.
6. Wszystkie awarie operacji przekazują przyczynę, identyfikator zadania i możliwość wejścia do logu. Brak dowodu ma stan UNKNOWN.
7. Konsole PTY oraz Output mają oddzielną semantykę; Output nie udaje interaktywnego terminala.
8. Działania niszczące wymagają zgodnych z backendem guardów i potwierdzeń; zamknięcie aplikacji nie zatrzymuje trwałego runtime.

## 3. Scenariusze odbioru

- A: czysty start, Technical Workbench, prawidłowe etykiety i brak fałszywych zielonych statusów.
- B: załadowanie starszej konfiguracji `violet-night`, brak samoczynnej migracji i uszkodzenia ustawień.
- C: przełączenie Technical → Operations → Fluent → Technical oraz ponowne uruchomienie okna, wybór zachowany.
- D: niezapisana zmiana pola MCP; próba wyboru stylu nie gubi tekstu.
- E: zmiana szerokości okna, lewa/prawa nawigacja, otwieranie dolnego dock, zachowanie układu w walidowanym JSON.
- F: niedostępny daemon lub brak danych → UNKNOWN i precyzyjny komunikat; nie fałszywy RUNNING.
- G: testy TPA z wynikiem syntetycznym nie oznaczają zakończonego manualnego odbioru.
- H: log z tokenem albo ścieżką prywatną jest redagowany według istniejącego kontraktu.
- I: brak Qt w interpreterze → jawna informacja o wymaganej, opcjonalnej zależności; brak automatycznej instalacji.
- J: klawiatura, fokus, kontrola DPI, długie polskie etykiety, jasna interpretacja błędów i stanów.
- K: pakowanie EXE i kontrola załączonych źródeł licencji; brak domyślnie dodanych nowych zależności.
- L: stany połączenia MCP (endpoint, OAuth, toolset, host, accepted turn) są osobno raportowane.

## 4. Decyzje integracyjne

Nie tworzymy osobnego procesu Jaźni do „podglądu” UX, nie kopiujemy MEMORY do testów, nie dodajemy drugiego MCP klienta ani nie pobieramy zależności podczas uruchamiania. Zmiana palet, metryk i opisów jest bezpieczna tylko wtedy, gdy istniejące testy `test_jazn_run_studio*.py`, `test_heart_system*.py`, `test_jazn_tpa_*.py` i docelowe testy Qt przejdą oraz operator odbierze realny interfejs na Windows.

Kolejne etapy rozbudowy: natywny pełny panel testów, rozdzielany monitor po prawej, bezpieczny eksport/import spersonalizowanej palety, ekran konfiguracji OAuth i workflow pamięci P4. Te funkcje **nie zostały zadeklarowane jako ukończone przez samą implementację profili**.
