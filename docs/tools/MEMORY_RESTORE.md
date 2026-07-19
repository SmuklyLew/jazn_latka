# Restore pamięci Jaźni — zgodność nazwy

Kanonicznym i jedynym programem operatorskim jest:

```powershell
py -X utf8 .\tools\memory_rebuild.py
```

Plik `tools/restore_memory.py` został usunięty w Memory Rebuild v24.0.2.04, aby nie utrzymywać dwóch rozbieżnych interfejsów wykonujących ten sam proces. Backend `latka_jazn.tools.memory_restore` pozostaje współdzielonym silnikiem używanym przez `memory_rebuild.py` i testy; nie jest drugim programem operatorskim.

Aktualny opis procesu, obsługiwanych eksportów, planu bez zapisu, walidacji i granic L2/L3 znajduje się w [`MEMORY_REBUILD.md`](MEMORY_REBUILD.md).
