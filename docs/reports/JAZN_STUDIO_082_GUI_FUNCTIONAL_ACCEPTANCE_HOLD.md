# Jaźń Studio .82 — checkpoint odbioru GUI i migracji (2026-10-24)

Ten checkpoint **nie** oznacza produkcyjnego odbioru. Wykonano audyt stanu PR #409–#416 oraz audyt wybranych testów Qt i ChatClient dla #416.

## Dowody wykonane / dostępne

- Ancestry GitHub: #409–#415 są przodkami #416; `master..#416`: 189 commitów na bazowym `.81`.
- Na `.81` 11 workflow przeszło dla commita kodowego `deb46969...`; dwa kolejne commity dotyczyły katalogu kontraktów i manifestów. Nie uznajemy tego za pełną finalną walidację HEAD.
- Potwierdzona przez operatora dwuturowa rozmowa CLI `.75` na izolowanym daemonie i Ollama `gemma3:latest`: wynik w `docs/reports/JAZN_STUDIO_LOCAL_CHAT_ENDPOINT_ACCEPTANCE.md`. To NIE jest odbiór GUI `.81`.
- Zgodnie z testami statycznymi i kodem: `ChatClient.connect()` przed poprawką rezerwował `chat` PRZED walidacją skonfigurowanego endpointu. `.82` zmienia kolejność; nowy test ma wykazać, że błędny endpoint nie pozostawia osieroconej rezerwacji.
- Dodano syntetyczne testy PySide6: dostarczenie finalnej odpowiedzi i ACK, ponowne załadowanie tego samego `session_id/request_id` i blokada wznowienia na obcym porcie. **Nie jest to live model acceptance.**
- `master`, działające instancje .42/.75, MEMORY i markery pozostają nietknięte. 

## Macierz pełnej zgodności funkcjonalnej 12 studiów (niezaliczone)

`tools/jazn_run_studio/STUDIO_MIGRATION.md` nadal definiuje 12 studiów: dziewięć częściowo zintegrowanych, trzy bez natywnej strony. Brak twardych dowodów pełnej migracji:
1. System — aktualizacje i audyty poznawcze
2. Start — pełny katalog zadań i konfiguracji
3. Konfiguracja — mapy ścieżek, preview/restore/dirty-state (ROOT config jest częściową integracją)
4. MEMORY — importy, afekt, kandydaci, protokół
5. MEMORY Rebuild — specjalistyczne dialogi, plan/progress
6. Testy — edytor review i historia
7. Generator pakietów — widoki planu/progress i trwałe ustawienia
8. Zależności — wizualizacja lock/install i Linux offline
9. Python Runtime — inwentarz i funkcjonalna zgodność
10. Version Rebuild — natywny Qt workflow nadal niewdrożony
11. Import/eksport rozmów — dedykowany Qt workflow nadal niewdrożony
12. Restore pamięci — dedykowany Qt plan/compare/restore nadal niewdrożony

Dla każdego modułu wymagane: before/after mapping, test pozytywny/błędny/integracyjny, ustawienia i backup, zachowanie bezpieczeństwa, rzeczywisty GUI Windows/Linux i dostępność. **Żaden nie może zostać automatycznie oznaczony jako ukończony.**

## Manualny gate na Windows — nie wykonano

Na oddzielnym, czystym checkout `.82` i workspace, przy wolnym porcie np. `8879`:
- zweryfikuj integralność i tożsamość pakietu oraz brak osieroconego markera; odczytaj ustawienia `$ROOT/jazn_system_config.json` bez ujawniania sekretów;
- z poziomu Studio uruchom daemon, potwierdź dokładny `active_root`, PID, `instance_id`, heartbeat i `ConversationReady`;
- `gemma3:latest`: pierwsza tura, następna tura z inną informacją, rozłącz/połącz, stable `session_id`, odrębny `request_id/turn_id/trace_id`, zaakceptowane GUI `final_visible_text`;
- zasymuluj przerwany transport, wznów **ten sam** request bez replay; dopiero potem restart wyłącznie tej testowej instancji i sprawdź przetrwanie sesji;
- osobno EXE/offline/vendor AV i rzeczywisty audyt klawiatury/DPI/focus.

Brak dostępu do okna Windows/operatora ⇒ te bramki **NOT RUN**.
Nie używaj cudzego procesu na portach 8787/8877 i nie usuwaj markera.

## Release gates

Weryfikacja automatyczna nowego HEAD przez GitHub Actions musi zakończyć się po synchronizacji metadanych i wszystkich testach. Następnie ewentualna poprawka i kolejne CI. PR #415 pozostaje Draft i nie wolno scalać go ani #416 z master bez osobnej zgody użytkownika. Starsze #409–#414 zamknąć dopiero po sprawdzeniu rzeczywistego merged ancestry.

Referencje: https://doc.qt.io/qtforpython-6.11/PySide6/QtTest/index.html ;
https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
