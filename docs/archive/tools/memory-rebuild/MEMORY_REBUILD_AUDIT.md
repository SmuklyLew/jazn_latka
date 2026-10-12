# Audyt Memory Rebuild v24.0.2.04

## Zakres przejrzany

| Obszar | Wynik |
|---|---|
| `chat_export_models.py` | rozszerzono opis członków kanonicznych i shared metadata |
| `chat_export_reader.py` | naprawiono wybór plików, rekordy bez `mapping`, części numerowane i duplikaty |
| `chat_export_importer.py` | dodano proweniencję członków i ostrzeżenia readera |
| `chat_export_dedupe.py` | istniejące relacje zachowane; bez zmiany |
| `chat_export_store.py` | transakcje i bezstratny payload zachowane; bez migracji schematu w tym wydaniu |
| `chat_export_topics.py` | analiza nadal uruchamiana dopiero po L0; bez zmiany |
| `memory_rebuild_coordinator.py` | usunięto pełne `json.loads` przy detekcji, zachowano kolejność operatora i poprawiono błędy etapów |
| `memory_restore_runner.py` | plan narastający, fingerprint źródeł, poprawne liczniki wykonania |
| `memory_restore_types.py` | kontrakty ustawień i preflight zachowane |
| `memory_restore_storage.py` | SQLite backup API i walidacja zachowane |
| `memory_rebuild_catalog.py` | katalog operacji i relacji zachowany |
| `memory_rebuild_journal*` | import i rewizje dziennika zachowane |
| `memory_rebuild_experience.py` | ręczna akceptacja i brak automatycznego L2/L3 zachowane |
| `source_archive_gateway.py` | read-only L0 i kontekst źródłowy zachowane |
| `tools/memory_rebuild.py` | wersja 24.0.2.04, chronologia źródeł, jeden kanoniczny entrypoint |
| `tools/restore_memory.py` | usunięty jako stary drugi program operatorski |

## Najważniejsze naprawione błędy

1. `shared_conversations.json` spełniał dawniej warunek `endswith("conversations.json")` i tworzył rozmowy bez wiadomości.
2. Duże eksporty z ponumerowanymi plikami rozmów nie miały pełnego wsparcia.
3. Każdy ZIP w planie był porównywany z tym samym stanem początkowym, więc nakładające się rozmowy były wielokrotnie liczone jako `new`.
4. Źródła były sortowane rozmiarem, który nie opisuje chronologii.
5. Bezpośredni JSON był wczytywany w całości tylko w celu rozpoznania typu.
6. Przygotowany plan nie był związany z późniejszym SHA-256 źródła.
7. Podsumowanie importu mogło błędnie oznaczyć etap jako poprawny po błędzie.
8. Pozostawały dwa programy operatorskie o nakładającej się funkcji.

## Świadomie odłożone

To wydanie nie zmienia schematu L0 w celu dodania jawnej tabeli pełnego tekstu ani pełnego blobu każdej historycznej rewizji. Obecny `payload_blob` nadal zachowuje aktywną, bezstratną rozmowę, a rewizje mają proweniencję i hashe. Migracja snapshotów powinna otrzymać osobny numer schematu, plan migracji i test rozmiaru na pełnym archiwum.

To wydanie nie automatyzuje L2/L3. Najpierw należy ukończyć i zweryfikować pełne L0, dziennik, segmentację oraz ręczny przegląd doświadczeń.
