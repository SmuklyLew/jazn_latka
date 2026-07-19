# Odbudowa pamięci Jaźni — Memory Rebuild v24.0.2.04

Kanonicznym programem operatorskim jest wyłącznie:

```powershell
py -X utf8 .\tools\memory_rebuild.py
```

Silnik pozostaje w `latka_jazn.tools.memory_restore`, lecz nie jest drugim programem dla operatora.
Narzędzie buduje i weryfikuje pięć baz:

```text
memory/sqlite/
├── archive_chats.sqlite3
├── journal.sqlite3
├── memory_jazn.sqlite3
├── experience.sqlite3
└── import_catalog.sqlite3
```

## Granica działania

- `archive_chats.sqlite3` jest bezstratnym L0 rozmów i ich gałęzi.
- `journal.sqlite3` przechowuje wpisy dziennika oraz rewizje.
- `experience.sqlite3` przechowuje kandydatów i ręcznie zatwierdzone doświadczenia.
- `memory_jazn.sqlite3` jest bazą L1/L2/L3 runtime.
- `import_catalog.sqlite3` zapisuje źródła, operacje, walidacje i relacje.

Import, analiza tematów ani utworzenie kandydata nie promują automatycznie treści do L2 lub L3.

## Źródła rozmów w v24.0.2.04

Reader rozróżnia trzy rodzaje danych:

1. `conversations.json` — kanoniczna historia rozmów.
2. Ponumerowane pliki rozmów, np. `conversations-001.json`, `conversations-002.json` — części jednego dużego eksportu, czytane w kolejności numerycznej.
3. `shared_conversations.json` — metadane udostępnionych linków: ID, conversation ID, tytuł i ustawienie anonimowości. Nie jest to treść rozmowy i nie może tworzyć pustych czatów.

Dopasowanie jest wykonywane po dokładnej nazwie pliku. Nazwy takie jak `my_conversations.json` nie są uznawane za kanoniczne źródło.

`chat.html` pozostaje pomocniczym źródłem mapy załączników. Sam HTML nie jest bezstratnym archiwum drzewa rozmowy.

## Plan bez zapisu

Plan jest narastającą symulacją:

1. tworzona jest tymczasowa kopia istniejącego `archive_chats.sqlite3`;
2. pierwszy ZIP jest planowany i symulacyjnie importowany wyłącznie do tej kopii;
3. drugi ZIP jest porównywany z wynikiem pierwszego;
4. kolejne źródła widzą wcześniejsze `new`, `identical`, `older_subset`, `extends_active` i konflikty;
5. katalog docelowy nie jest modyfikowany.

Dzięki temu liczników z wielu ZIP-ów nie sumuje się tak, jakby każdy był porównywany z pustą bazą.

Plan zapisuje SHA-256 i rozmiar każdego źródła. Wykonanie jest blokowane, gdy plik zmieni się po planowaniu.

## Kolejność źródeł

Jawna kolejność wybrana przez operatora jest zachowywana, a powtórzona ścieżka jest usuwana bez zmiany pierwszego wystąpienia.

Dla automatycznego wyboru wszystkich plików program używa daty `YYYY-MM-DD`, `YYYY.MM.DD` albo `YYYY_MM_DD` z nazwy lub ścieżki. Rozmiar pliku nie jest traktowany jako chronologia. Gdy daty nie ma, używana jest stabilna kolejność nazw.

## Walidacja rekordów

Rekord rozmowy musi mieć:

- identyfikator rozmowy;
- niepuste drzewo `mapping`;
- poprawne węzły i role możliwe do zbudowania przez reader.

Rekord bez `mapping` jest raportowany jako metadany i pomijany. Jeżeli dwa ponumerowane pliki zawierają identyczną rozmowę, druga kopia jest pomijana z ostrzeżeniem. Rozbieżne wersje tego samego ID w jednym eksporcie blokują import i wymagają kontroli.

ZIP jest sprawdzany pod kątem CRC, niebezpiecznych ścieżek, powtórzonych nazw i kolizji wielkości liter.

## Zalecana kolejność odbudowy

1. Utwórz nowy pusty katalog testowy.
2. Wybierz wszystkie eksporty rozmów w kolejności chronologicznej.
3. Uruchom plan bez zapisu i sprawdź źródła odrzucone.
4. Sprawdź liczniki relacji każdego kolejnego ZIP-a.
5. Uruchom odbudowę L0.
6. Ponownie zaimportuj wybrany ZIP i potwierdź idempotencję.
7. Uruchom pełne `verify`: `integrity_check=ok` i pusty `foreign_key_check` dla wszystkich baz.
8. Zaimportuj i zweryfikuj dziennik.
9. Dopiero po skompletowaniu L0 uruchom analizę tematów.
10. Utwórz małą próbkę kandydatów doświadczeń i przeglądaj ją ręcznie.
11. L2 i L3 odbudowuj osobnym, jawnym procesem promocji.

## Tryby celu

### Developer

Cel musi znajdować się poza repozytorium. Domyślny token zapisu:

```text
RESTORE
```

### System

Wymaga pełnego runtime, poprawnego `doctor`, aktualnej integralności oraz zatrzymanego daemona. Token jest związany z dokładną ścieżką:

```text
SYSTEM_RESTORE:<bezwzględna ścieżka>
```

## Raporty

Każdy przebieg zapisuje osobny katalog z:

- `settings.json`;
- `plan.json`;
- `events.jsonl`;
- raportem każdego importu;
- pełną walidacją;
- `summary.json`;
- opcjonalnym porównaniem do testów bazowych.

Podsumowanie podaje osobno liczbę źródeł zaplanowanych i wykonanych. Etap z błędem nie może zostać oznaczony jako poprawny.

## Granice bezpieczeństwa

- brak automatycznego zatwierdzania doświadczeń;
- brak automatycznej promocji L2/L3;
- sceny książkowe i roleplay nie stają się wydarzeniami fizycznymi;
- sny i wizje pozostają materiałem symbolicznym;
- surowe źródła nie są zmieniane;
- plan nie zapisuje do celu;
- zmiana źródła po planie blokuje wykonanie;
- błąd domyślnie zatrzymuje dalszy import;
- `continue_on_error` wymaga jawnego włączenia.
