# Memory Rebuild — Test00 Source Fidelity i Recall baseline

## Test00

Test00 zapisuje dokładne bajty źródeł do lokalnej, chunkowanej bazy kontrolnej i niezależnie sprawdza struktury rozmów.

Domyślna lokalizacja:

```text
./memory/rebuild_tests/test_00/<run-id>/
```

Uruchomienie z jawnymi plikami:

```powershell
py -X utf8 .\tools\memory_rebuild.py test00 `
  D:\PRIVATE\chatGPT-export-2025.06.30-conversations.json `
  D:\PRIVATE\chatGPT-export-manual-2025.07-chat.html
```

Albo z enabled sources projektu:

```powershell
py -X utf8 .\tools\memory_rebuild.py `
  --project <ID-lub-nazwa> `
  test00
```

Statusy:

- `PASSED` — raw round-trip i structural census są bez strat;
- `LOSSY` — źródło jest zachowane bajtowo, ale strukturalny parser jest niepełny, np. rendered HTML fallback;
- `BLOCKED` — format zachowano, ale nie ma wymaganej interpretacji;
- `FAILED` — błąd integralności lub różnica raw/parsed.

`source_mirror.sqlite3` nie jest `memory_jazn.sqlite3` i nie jest czytany przez runtime Recall.

## Recall baseline

Benchmark pozostaje prywatnym plikiem poza Git. Schemat v2:

```json
{
  "schema_version": "jazn_memory_recall_benchmark/v2",
  "suite_id": "private-baseline-01",
  "minimums": {
    "recall_at_20": 0.0,
    "abstention_accuracy": 1.0,
    "max_false_memory_rate": 0.0,
    "max_sensitive_leakage_rate": 0.0
  },
  "cases": [
    {
      "id": "case-001",
      "category": "direct",
      "query": "prywatne pytanie",
      "expected_any": ["prywatny termin"],
      "limit": 20
    },
    {
      "id": "case-negative",
      "category": "negative",
      "query": "pytanie bez dowodu",
      "expected_abstain": true,
      "minimum_hits": 0,
      "limit": 20
    }
  ]
}
```

Uruchomienie:

```powershell
py -X utf8 .\tools\memory_rebuild.py recall-baseline `
  --database D:\PRIVATE\memory_jazn.sqlite3 `
  --benchmark D:\PRIVATE\recall.private.json
```

Wyniki domyślnie:

```text
./memory/rebuild_tests/recall/<run-id>/
  recall.private.json
  recall.sanitized.json
```

Baseline ma identyfikator `fts5-bm25/v1` i zawsze używa:

```text
layers = L0 only
require_provenance = true
use_embeddings = false
training = false
```

Mierzone są m.in. Recall@k, MRR, nDCG, abstention, false-memory, provenance, temporal i sensitive leakage.

`recall.sanitized.json` nie zawiera surowych pytań, oczekiwanych fraz ani zwróconych treści.

## Co nie jest jeszcze wdrożone

- query rewrite A/B;
- dense retrieval;
- reranker;
- trening retrievera;
- automatyczna promocja L2/L3;
- aktywacja pamięci.

Te etapy wymagają osobnego source gate i mierzalnej przewagi nad zachowanym baseline FTS5.
