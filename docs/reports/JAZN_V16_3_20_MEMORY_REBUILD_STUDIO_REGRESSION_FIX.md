# Jaźń v16.3.20 — Memory Rebuild Studio regression fix

## Cel

Domknięcie regresji wykrytych przez pełny deterministic test suite po konwergencji Memory Rebuild do jednego kanonicznego `studio.py`.

## Naprawione kontrakty

- strona **TESTY** ponownie pokazuje osobną sekcję **DOWODY** pomiędzy WYNIKIEM i WYJŚCIAMI;
- gdy test był uruchomiony, Studio pokazuje dostępne identyfikatory dowodowe (`run_id`, `database_sha256`, `baseline_id`, `sanitized_report`, `quality_gate_passed`); gdy nie był uruchomiony, stan jest jawnie opisany;
- strona **USTAWIENIA → Wszystkie ustawienia** ponownie pokazuje pełny stan subsystemu Recall, w tym `model_training: NIE [READ-ONLY / ZABLOKOWANE]`;
- widok Recall odzyskał jawne metryki benchmarku: Recall@k, MRR, nDCG, abstention, provenance, temporal/update, false-memory i sensitive leakage;
- numer widocznego Studio został zsynchronizowany do `memory-rebuild-studio/v16.3.20`;
- testy release i regresji zostały zsynchronizowane z `16.3.20-memory-rebuild-unified-studio-regression-fix`.

## Granice

Ta poprawka nie włącza treningu modelu, dense retrieval, query rewrite ani rerankera. Nie zmienia także fail-closed blokad automatycznego experience/L2/L3/activation i nie dodaje prywatnych danych do repozytorium.

## Weryfikacja

Kanonicznym kryterium akceptacji pozostają workflow PR dla jednego końcowego SHA: `release-hardening`, `memory-rebuild-v24-windows` oraz `persistent-runtime-e2e`. PR nie powinien być scalany przed pełnym zielonym wynikiem.
