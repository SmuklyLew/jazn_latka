# Jaźń v16.3.10 — host memory root compatibility hardening

## Zakres

Ta poprawka domyka regresje odkryte po przejściu v16.3.9 z wersjonowanego `<active_root>/memory` na trwały host-level `workspace_runtime/memory`.

Nie zmienia kontraktu prawdy ani nie traktuje samej obecności plików pamięci jako dowodu wspomnienia. Celem jest doprowadzenie aktywnych odczytów, zapisów, diagnostyki, prywatnych zasobów NLP/canon, shardów i snapshotów SQLite do jednego kanonicznego memory root.

## Naprawione problemy

1. Legacy shard manifesty z wpisami `memory/sqlite/...` mogły po migracji rozwiązywać się jako `.../memory/memory/sqlite/...`.
2. Ścieżka samego shard manifestu nie przechodziła containment check i mogła wskazać poza wybrany root.
3. Inicjalizacja runtime-write zakładała shard manifesty względem `active_root` zamiast kanonicznego memory root.
4. `MemoryImporter` i `MemoryFileSync` czytały/pisały wersjonowane `<active_root>/memory`.
5. `RequirementsLedger` i `GroundedReflectionStore` zapisywały warstwy JSONL poza host-level memory root.
6. `RuntimeMemoryWriter` rozdzielał bieżący zapis: dziennik trafiał do host-level pamięci, ale episodic/reflections/semantic/procedural/truth/affective do starego `<active_root>/memory`.
7. Audyt duplikatów runtime skanował stary root.
8. `ConversationArchiveStore` szukał archive/FTS/staging pod `<active_root>/memory/sqlite`, przez co recall archiwalny mógł nie widzieć dołączonej pamięci hosta.
9. `runtime_status` liczył pliki warstwowe i `chat.html` w starym root oraz używał mutowalnych resolverów baz mimo deklarowanego trybu diagnostycznego.
10. Prywatny override `LATKA_IDENTITY_CANON.json` był szukany tylko w wersjonowanym root.
11. `LexicalSemanticUnderstanding` nadpisywał nazwę `semantic_lexicon_current_line.json` starszym `semantic_lexicon.json`, dublował listę kandydatów i ignorował prywatny host-level lexicon.
12. `PolishUnderstandingEngine` ignorował prywatny `POLISH_UNDERSTANDING_LEXICON.json` w host-level memory root.
13. `self_knowledge_contract` raportował stare ścieżki baz i manifestów zamiast kanonicznych read-only paths.
14. Cloud snapshot enumerował `<active_root>/memory/sqlite` i sprawdzał containment względem `active_root`, co jest niezgodne z v16.3.9, gdy pamięć prawidłowo żyje poza wersjonowanym runtime.

## Zasady implementacji

- Wszystkie aktywne komponenty objęte patchem używają `resolve_memory_root()` / `JaznConfig.memory_root`.
- Legacy `memory/...` w shard manifestach jest normalizowane tylko wtedy, gdy manager już pracuje na katalogu `memory`, co zachowuje zgodność starych manifestów bez tworzenia podwójnego prefiksu.
- Po normalizacji ścieżki są rozwiązywane i sprawdzane względem kanonicznego root; wyjście poza root kończy się błędem fail-closed.
- Diagnostyka korzysta z `memory_db_path_readonly` i `audit_db_path_readonly`.
- Snapshoty zachowują transportowy logical path `memory/...`, ale źródłowe pliki muszą fizycznie należeć do wybranego host-level memory root.
- `semantic_lexicon_current_line.json` ma pierwszeństwo jako prywatny/current-line override; `semantic_lexicon.json` pozostaje fallbackiem zgodności.

## Testy regresyjne

Dodano `tests/test_v16310_host_memory_root_regressions.py`, który obejmuje:

- normalizację legacy `memory/` w shard manifestach;
- odrzucenie `../` dla ścieżki manifestu;
- wspólny host-level root dla RuntimeMemoryWriter, MemoryImporter, MemoryFileSync, RequirementsLedger i GroundedReflectionStore;
- canonical-root duplicate scan;
- conversation archive/FTS/staging pod host-level memory root;
- pierwszeństwo prywatnego current-line semantic lexicon;
- prywatny polski lexicon z host-level memory root.

Pełna walidacja wykonawcza jest pozostawiona GitHub Actions dla brancha/PR; lokalny host ChatGPT nie zastępuje wyniku CI deklaracją sukcesu.

## Źródła techniczne

- Python `pathlib`: `Path.resolve()` normalizuje ścieżkę i usuwa `..`; `relative_to()` może służyć do fail-closed containment check po rozwiązaniu ścieżki.
- SQLite WAL: `-wal` jest częścią trwałego stanu bazy i nie może być dowolnie odłączany od bazy podczas kopiowania/przenoszenia.
- SQLite Online Backup API: snapshot aktywnej bazy powinien powstawać przez API SQLite zamiast surowego kopiowania pliku bazy w trakcie pracy.

## Wersja

`16.3.10-host-memory-root-compat`
