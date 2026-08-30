# Jaźń v16.0.4 — Runtime Turn Liveness CI Hardening

## Zakres

Ta poprawka domyka statyczny kontrakt typów po refaktorze `memory_package_attach.py` z v16.0.3.

## Naprawa

`RuntimePreflightReport.version` jest formalnie typu `str | None`. Poprawny `manifest_ok=True` wymaga wersji, ale Pyright nie przenosi tej zależności między polami dataclass. Zamiast rzutowania lub `type: ignore`, `attach_memory_package()` jawnie zawęża `preflight.version`: brak wersji po pozytywnych bramkach struktury, manifestu i provenance kończy attach stanem `runtime_not_verified` i zapisuje `runtime_preflight_version_missing=true` w raporcie.

Dzięki temu `_finalize_memory_attach()` otrzymuje wyłącznie zweryfikowany `str`, a granica prawdy runtime pozostaje fail-closed.

## Wersja

Zgodnie z zasadą projektu każda dodatkowa poprawka systemowa podnosi numer Jaźni. Wersja kanoniczna: `16.0.4-runtime-turn-liveness-ci-hardening`.
