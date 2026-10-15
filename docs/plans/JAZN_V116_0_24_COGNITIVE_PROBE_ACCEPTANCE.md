# v116.0.24 — źródłowo bezpieczna ewaluacja P0B/P1/P2/P3/P4

Status: **zaimplementowane operacyjne sondy, NIE pełna autonomiczna realizacja P1–P4**.

## Komenda Autora
```powershell
python -X utf8 tools/jazn_studio.py --cognitive-audit
```
Raport działa tylko w pamięci procesu, nie uruchamia daemona, nie zapisuje SQLite, nie łączy się z siecią i nie promuje pamięci.

## Funkcje sprawdzalne
- **P0B:** `evaluate_intents` wykonuje aktywny `DialogueIntentClassifier` na opisanych przypadkach i raportuje również pomyłki. Prawdziwa niezależna ocena wymaga oddzielnego, nieużywanego podczas rozwoju zestawu.
- **P1:** `assess_source_claim` sprawdza digest SHA256, lineage i typ źródła względem istniejącej `TypedMemorySourcePolicy`. Wprost raportuje, że nie zbadał fizycznej bazy danych ani autobiograficznego recall.
- **P2:** `regulate_with_ablation` porównuje decyzje istniejącego `HomeostasisRegulator` na dwóch syntetycznych stanach, sprawdza wpływ na wymaganie weryfikacji i budżet narzędzi. To test regulatora, nie uczucia.
- **P3:** `calibration_metrics` liczy Brier i ECE dla jawnie oznaczonych, opisanych par; nie oznacza heurystycznego `confidence` jako skalibrowanego. `rest_safety_contract_probe` sprawdza domyślne brak auto-L3 i brak zewnętrznego sprawstwa; nie wykonuje Rest/Dream.
- **P4:** tryb Jaźń Studio `--cognitive-audit` prezentuje maszynowo czytelny snapshot, bez nowego runtime i bez mutacji prywatnych danych.

## Nadal wymagane przed ogłoszeniem P1–P4 jako `live_verified`
P0B: niezależny test kontekstów wieloturowych i zgodności odpowiedzi z pytaniem; P1: prywatny, podpisany MEMORY attach, restart, odczyt provenance i fałszywe wspomnienia; P2: porównanie naturalności z rzeczywistymi LLM i dłuższą rozmową; P3: niezależne próbki kalibracyjne, sesje Replay/Dream i efekt na Recall; P4: odbiór okien GUI na Windows i integracja z istniejącym katalogiem testów. Żadne z tych kryteriów nie jest automatycznie zaliczone przez sondy.

Źródła: https://airc.nist.gov/airmf-resources/playbook/measure/ ; https://pubmed.ncbi.nlm.nih.gov/10789197/ ; https://doi.org/10.1146/annurev-psych-022423-032425
