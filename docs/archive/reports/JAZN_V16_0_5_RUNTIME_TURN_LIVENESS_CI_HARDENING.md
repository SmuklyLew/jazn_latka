# Jaźń v16.0.5 — Runtime Turn Liveness CI Hardening

## Zakres

Ta poprawka domyka pełny deterministic suite po naprawie Pyright z v16.0.4.

## Naprawa audytu aktywnej linii

`tests/test_v1601_memory_transport_generator.py` celowo używa historycznej wersji wskazywanej przez `LEGACY_MEMORY_SOURCE_VERSION` jako próbki wejściowej do testu repacku pamięci legacy. `current_line_archive_audit` traktował literal tej kontrolowanej próbki jak przypadkową starą referencję aktywnego runtime.

Zamiast wyłączać audyt albo rozszerzać granicę wersji, dodano wyłącznie ten konkretny test do istniejącej, restrykcyjnej listy `APPROVED_LEGACY_SOURCE_PATHS`. Wyjątek nadal działa tylko dla dokładnego `LEGACY_MEMORY_SOURCE_VERSION` i linii jawnie oznaczonej jako `legacy`/`baseline`, więc inne stare referencje pozostają błędem.

## Wersja

Zgodnie z zasadą projektu dodatkowa poprawka systemowa podniosła kanoniczną wersję do linii 16.0.5 `runtime-turn-liveness-ci-hardening`.
