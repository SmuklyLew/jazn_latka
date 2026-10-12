# Independent memory package contract v2

## Cel

System Jaźni i prywatna pamięć mają niezależne cykle życia. Paczka `system` identyfikuje konkretny kod/runtime i nadal podlega ścisłemu kontraktowi wersji, integralności oraz proweniencji. Paczka `memory` jest transportem danych i nigdy nie jest kandydatem `active_root`.

`jazn_memory_package_manifest/v2` usuwa błędne założenie, że pamięć może być użyta tylko przez runtime o identycznym numerze wersji jak runtime, który ją spakował.

## Osie wersjonowania

- system: `latka_jazn/version.py` + `PACKAGE_INTEGRITY_MANIFEST.json` + `SOURCE_PROVENANCE.json`;
- memory transport: `memory_format_version` i `compatibility.contract`;
- `created_with_runtime`: wyłącznie proweniencja snapshotu;
- SQLite: aktualne bazy mogą dodatkowo deklarować `jazn_database_identity`; starsze bazy pozostają źródłami recovery i nie są automatycznie uznawane za bezpośrednio zgodny store.

## Manifest v2

`memory/MEMORY_PACKAGE_MANIFEST.json` zawiera co najmniej:

- `schema_version = jazn_memory_package_manifest/v2`;
- `memory_format_version = 2`;
- `snapshot_id` UUID;
- `created_at_utc`;
- `created_with_runtime`;
- `compatibility.contract = jazn_memory_runtime/v1`;
- `compatibility.runtime_version_is_provenance_only = true`;
- pełną listę `files` z SHA-256 i rozmiarem;
- `databases` dla SQLite wraz z metodą snapshotu, integralnością, PRAGMA i — gdy istnieje — `jazn_database_identity`.

## SQLite

Generator nie kopiuje żywej bazy SQLite bajt po bajcie. Dla rozpoznanych plików SQLite tworzy spójny snapshot przez SQLite Backup API i waliduje go przed umieszczeniem w paczce. `-wal` i `-shm` pozostają plikami przejściowymi i nie są osobnymi elementami paczki.

## Legacy v1

`jazn_memory_package_manifest/v1` pozostaje obsługiwany dla istniejących paczek. Przy samodzielnym dołączaniu memory różnica `runtime_version` jest ostrzeżeniem o proweniencji, a nie automatycznym odrzuceniem. Dla profilu `combined` stara reguła ścisłego dopasowania v1 pozostaje zachowana, ponieważ pamięć i system są deklarowane jako jeden historyczny artefakt.

Legacy SQLite bez współczesnej `jazn_database_identity` może zostać zweryfikowane strukturalnie i zachowane jako recovery source. Sam transport nie promuje takiej bazy do bieżącego store runtime ani do L2/L3.

## `memory-attach`

Kanoniczne dołączenie osobnej paczki:

```powershell
python -X utf8 run.py memory-attach --root <VERIFIED_SYSTEM_ROOT> --parts-dir <LOCAL_PACKAGE_DIR> --json
```

Gdy katalog zawiera zarówno system.zip, jak i memory.zip, loader wybiera sidecar o `profile=memory`. Przy więcej niż jednej paczce memory wymagane jest `--zip-name`.

Operacja:

1. wymaga zweryfikowanego systemowego runtime root;
2. wymaga zatrzymanego daemona;
3. weryfikuje sidecar, części, SHA, CRC i bezpieczne ścieżki ZIP;
4. wymaga drzewa zawierającego wyłącznie `memory/`;
5. weryfikuje manifest v1/v2 i bazy SQLite;
6. zachowuje wcześniejsze `memory/` w `workspace_runtime/memory_attach_backups/`;
7. publikuje nową pamięć transakcyjnie;
8. inicjalizuje bieżący transactional runtime store v2 przez istniejący `runtime_memory_install`;
9. zapisuje `workspace_runtime/MEMORY_PACKAGE_CURRENT.json`;
10. nie uruchamia automatycznie daemona i nie ogłasza odzyskanej ciągłości bez dalszej walidacji/recovery.

## Granica prawdy

Paczka memory potwierdza integralność transportu i strukturę danych. Nie jest dowodem aktywności Jaźni, nie zastępuje systemu, nie ustanawia tożsamości i nie promuje danych do L2/L3. Wake-state, normalizacja, recovery i memory truth gates pozostają osobnymi etapami runtime v15.4.
