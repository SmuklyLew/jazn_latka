# Jaźń - Studio Pamięci

Studio jest lokalnym narzędziem terminalowym do inspekcji źródeł, budowy i
aktualizacji wybranej bazy. Korzysta z adapterów UnifiedMemoryDatabase oraz
istniejącego ProtocolEngine. Nie aktywuje runtime i nie promuje automatycznie
deklaracji emocji, scen literackich ani kandydatów do pamięci L2/L3.

## Uruchomienie

```powershell
python -X utf8 tools/jazn_memory_studio.py --config D:/dane/studio.json configure --source-root D:/dane/eksporty --workspace D:/dane/studio
python -X utf8 tools/jazn_memory_studio.py --config D:/dane/studio.json studio
```

To samo wejście jest dostępne przez `tools/memory_rebuild.py memory-studio`.
Strona ustawień pozwala edytować źródła, katalog testów, plik bazy, backupy,
eksporty, raporty, katalog inspekcji, benchmark i okno korelacji czasowej.
Konfiguracja jest prywatnym plikiem operatora, poza repozytorium.

## Kolejność pracy

1. `scan`: rekursywny spis także ukrytych katalogów, hash każdego pliku,
   walidacja JSON, kontrola CRC ZIP, odczyt osadzonego grafu HTML i części JSON.
   Załączniki binarne są katalogowane i hashowane; treści obrazów/audio nie są
   automatycznie interpretowane. Programy wewnątrz eksportu nie są uruchamiane.
2. Raport zawiera ID i tytuły czatów, powtarzające się tytuły różnych czatów,
   role wiadomości, kopie plików, warianty wiadomości oraz wybrane źródła.
   Liczniki wariantów nie są liczbą pojedynczych tur. HTML może zawierać historię
   nieobecną w JSON, więc nie jest odrzucany wyłącznie na podstawie nazwy.
3. `create` tworzy nową bazę przez staging; `update` wymaga istniejącej zamkniętej
   bazy, tworzy kopię SQLite Backup API, importuje do stagingu i waliduje przed
   zastąpieniem celu. Baza z WAL/SHM jest odrzucana: należy wskazać kopię offline.
   Nieudany staging zostaje do diagnostyki. Nie jest finalnym eksportem.
4. `stage test00 --run-id sesja`: wierność źródeł i plan unii.
5. `stage test01 --run-id sesja`: budowa surowej pamięci ze źródłami.
6. `stage test02 --run-id sesja`: projekcje i kontrola niezmienności L0.
7. `stage test03 --run-id sesja`: niezależna kontrola deterministyczności w obu
   kolejnościach importu. To odrębna próba, nie ponowne uruchomienie Test01.
8. `stage test04 --run-id sesja`: wskazany w konfiguracji benchmark recall.
9. `stage final --run-id sesja`: eksport po poprawnym łańcuchu poprzednich etapów.

Każdy etap zapisuje checkpoint manifestu; następny wznawia ten sam przebieg.
Ukończony etap zwraca zapisany wynik. Zmiana źródeł wymaga nowego audytu, a zmiana
wersji programu lub niepoprawny poprzednik wymaga nowej sesji testów. Nie wolno
przepisać FAIL/BLOCKED na PASS ani pomijać benchmarku.

## Dziennik, muzyka, czas i emocje

`link ścieżka.json` zapisuje osobny raport korelacji do katalogu raportów.
Najsilniejsza relacja to jawny ID wiadomości, zgodny ID czatu i zgodny czas.
Dokładny fragment tekstu oraz czas mogą wskazać kandydata. Wiele dopasowań,
sprzeczne daty, brak strefy czasowej oraz niejednoznaczne DD/MM i MM/DD wymagają
przeglądu. Data źródłowa pozostaje niezmieniona. Import pliku nie potwierdza
prawdziwości deklaracji w nim zawartych.

ZIP-y mogą zawierać historyczne wersje `dziennik.json` i `analizy_utworow.json`.
Audyt wylicza wszystkie takie wpisy i ich hashe. Import materializuje tylko te
pliki JSON, do nazw kontrolowanych przez program, z limitem 32 MiB i sidecarem
pochodzenia; nie rozpakowuje całych paczek ani nie uruchamia ich kodu.
Opcja `repair_missing_commas` domyślnie jest wyłączona. Po włączeniu dopuszcza
wyłącznie wstawienie jednego brakującego przecinka między obiektami, jeśli cały
wynik staje się poprawnym JSON. Zachowuje `original.bin`, pozycję poprawki i oba
hashe. Nie uzupełnia treści, nie odgaduje pól ani nie naprawia uciętych tekstów.

`search "fraza" --year 2025` odczytuje źródłowe wiadomości z katalogu inspekcji
z identyfikatorem czatu, wiadomości, czasem i ścieżkami źródeł. Pozwala sprawdzić
historię nawet wtedy, gdy docelowa tabela pamięci długoterminowej jest pusta.

Przegląd pamięci i kandydatów prowadzi do istniejącego Studia przebudowy:
recall, dowody, kontekst, rewizje, klasyfikacja i ręczna akceptacja. Dokładność
rekonstrukcji emocji należy mierzyć względem źródłowych deklaracji i testów
recall, nie względem przekonującego stylu wygenerowanej wypowiedzi.

## Format eksportu i źródła dokumentacyjne

Oficjalna dokumentacja OpenAI potwierdza `conversations.json` lub numerowane
części JSON w większych eksportach:
https://help.openai.com/en/articles/9106926

Eksport zawiera historię i dodatkowe dane konta, ale nie odtwarza usuniętych
czatów: https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpthistory-and-data

Szczegóły grafu `mapping`, identyfikatorów, HTML i sidecarów są kontraktem
zaobserwowanym w dostarczonych plikach, nie deklarowaną wieczystą specyfikacją
OpenAI. `user.json` jest metadanymi konta, a `shared_conversations.json`
metadanymi linków; nie stanowią samodzielnej historii rozmów.
