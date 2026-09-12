# Jaźń v16.0.3 — Runtime Turn Liveness CI Hardening

## Zakres

Ta aktualizacja domyka wdrożenie pełnego payloadu v16.0.2 `runtime-turn-liveness-hardening` oraz naprawia odziedziczone błędy Pyright blokujące `release-hardening`.

## Domknięcie payloadu v16.0.2

Do gałęzi wchodzą wszystkie elementy zweryfikowanego patcha SHA-256 `23f89cf8adee86aece7db87c4211c24e29612a9c2314787f74d6876af3426f8c`:

- polityka pamięci dla pytań o doświadczenia i poprzedni rok,
- odrzucanie rozmownych wypełniaczy przez `MemorySearchPlanner`,
- jawny `daemon_turn_execution_timeout` w host bridge,
- diagnostyka `last_terminal_job` i `process_liveness` w daemonie,
- rozszerzenie listy dozwolonych historycznych referencji migratora,
- testy regresyjne `test_v1602_runtime_turn_liveness.py`,
- aktualizacja testu kontraktu wydania.

Transport `.jazn_upgrade_transport/v1602-runtime-turn-liveness/` i tymczasowy workflow `apply-v1602-runtime-turn-liveness.yml` są usuwane po materializacji zmian.

## Naprawy Pyright

### `memory_package_attach.py`

Monolityczny `attach_memory_package()` został rozdzielony na małe, jawnie typowane etapy: wybór źródła, weryfikację i ekstrakcję paczki, materializację segmentów JSONL, transakcyjną instalację pamięci i finalizację markera. Zmiana zachowuje dotychczasowy kontrakt wyników i rollbacku, a usuwa błąd `Code is too complex to analyze`.

### `memory_package_legacy_repack.py`

Kontrakt strumieni binarnych został ujednolicony z rzeczywistym typem zwracanym przez `zipfile.ZipFile.open()`: `IO[bytes]` zamiast węższego `BinaryIO`. Usuwa to trzy błędy `IO[bytes]` ↔ `BinaryIO` bez rzutowań i bez wyciszania diagnostyki.

## Wersja

Ponieważ naprawa Pyright jest dodatkowym patchem systemowym ponad payload v16.0.2, kanoniczna wersja zostaje podniesiona do `16.0.3-runtime-turn-liveness-ci-hardening`.
