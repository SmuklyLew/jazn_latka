# Memory Rebuild v16+ — architektura modularna i kontrakt bezpieczeństwa

## Status

Kanonicznym punktem wejścia jest `tools/rebuild_memory.py`. Poprzednia nazwa
`tools/memory_rebuild.py` pozostaje cienkim launcherem zgodnościowym i wywołuje
ten sam composition root. Kod startowy nie zawiera parserów, SQL, motywu ani
ustawień.

Wersja tej architektury:

- narzędzie: `memory-rebuild/v16.1`;
- aplikacja: `3.0.0`;
- zunifikowany schemat: `jazn_unified_memory/v3.0`;
- wspólne L0: `memory_rebuild_l0/v16.1`;
- pakiet Jaźni: `16.3.2-memory-rebuild-modular-typed-retrieval`.

## Podział kodu

| Odpowiedzialność | Moduł |
|---|---|
| cienkie launchery | `tools/rebuild_memory.py`, `tools/memory_rebuild.py` |
| composition root i routing poleceń | `memory_rebuild_app/entrypoint.py` |
| stałe i wykrywanie repozytorium | `memory_rebuild_app/config.py` |
| walidowane ustawienia | `memory_rebuild_app/settings.py` |
| wyłącznie wygląd i etykiety UI | `memory_rebuild_app/theme.py` |
| wspólny model pośredni | `memory_rebuild_app/intermediate.py` |
| adaptery formatów | `memory_rebuild_app/adapters/` |
| schemat i zapis L0 | `schema_l0.py`, `l0_store.py` |
| typowane API Łatki | `typed_api.py` |
| opcjonalna granica embeddingów | `embeddings.py` |

`settings.py` nie może wyłączyć FTS5 ani włączyć automatycznego L2, L3 lub
aktywacji. `theme.py` nie ma dostępu do bazy ani do decyzji polityki.

## Przepływ importu

Każdy format przechodzi przez ten sam kontrakt:

```text
plik/ZIP/SQLite
    -> SourceProbe
    -> format-specific ImportAdapter
    -> PreparedSource + strumień IntermediateRecord
    -> wersjonowany UnifiedL0Store
    -> jedna memory_jazn.sqlite3
    -> opcjonalna zgodnościowa projekcja do tabel rozmów/dziennika
```

Adaptery są osobne dla:

- HTML, w tym osadzony `jsonData` i widoczny fallback;
- kanonicznych eksportów ChatGPT JSON, katalogów oraz ZIP;
- dziennika JSON/JSONL/NDJSON;
- analiz utworów JSON;
- starych baz SQLite otwieranych tylko do odczytu.

Formaty nie zapisują bezpośrednio do wspólnej tabeli. Produkują typowane
`IntermediateRecord`, a jeden writer nadaje rewizje, zapisuje proweniencję i
utrzymuje FTS5. Zgodnościowe tabele rozmów i dziennika pozostają w tym samym
fizycznym pliku SQLite.

## Jedna baza i warstwy

`memory_jazn.sqlite3` zawiera dwa jawnie odseparowane zakresy:

- `memory_l0_*` — archiwum źródłowe, nieaktywne i wersjonowane;
- `memory_records` oraz indeksy tierów — pamięć aktywna L1/L2/L3.

Widok `memory_l0_current` pokazuje tylko bieżącą rewizję każdego logicznego
rekordu. Poprzednie rewizje pozostają w `memory_l0_records`. Widok
`music_analysis_current` jest logiczną kolekcją analiz utworów w tej samej
bazie, nie drugim plikiem SQLite.

Pole `is_current_revision` oznacza jedynie aktualną wersję dokumentu w L0. Nie
oznacza aktywacji pamięci.

## FTS5 i embeddingi

FTS5 jest obowiązkowe. Inicjalizacja kończy się błędem, jeżeli SQLite nie może
utworzyć `memory_l0_fts`. Walidacja wykonuje zarówno `integrity-check`, jak i
rzeczywiste zapytanie `MATCH` na jednorazowej migawce bazy.

Embeddingi są wyłączone domyślnie. Ich włączenie wymaga jednocześnie:

1. `embeddings_enabled: true`;
2. jawnej nazwy modelu;
3. przekazania providera implementującego typowany `EmbeddingProvider`;
4. zapisanych wektorów zgodnych z modelem i wymiarem.

Brak embeddingów nie degraduje działania podstawowego — recall używa FTS5.

## Typowane API recall

Łatka i adapter hosta powinny używać `TypedMemoryAPI`, nie wykonywać SQL:

```python
from latka_jazn.tools.memory_rebuild_app import RecallQuery, TypedMemoryAPI

response = TypedMemoryAPI("memory_jazn.sqlite3").recall(RecallQuery(
    text="latarnia ze spaceru",
    temporal_start="2025-01-01T00:00:00+00:00",
    temporal_end="2026-12-31T23:59:59+00:00",
))
```

Domyślnie przeszukiwane jest wyłącznie L0. Pamięć aktywna wymaga jawnego
`layers=(MemoryLayer.ACTIVE,)` albo dołączenia tej warstwy. Wynik zawiera
typowane cytowanie: identyfikator źródła, adapter, SHA-256, rekord źródłowy,
rewizję oraz przedział czasu.

Gdy nie ma temporalnie zgodnego rekordu z wymaganą proweniencją, API zwraca
`RecallStatus.UNKNOWN`, `known=False` i pustą listę trafień. Nie zgaduje i nie
zamienia braku dowodu w wspomnienie.

CLI udostępnia ten sam kontrakt:

```powershell
python -X utf8 .\tools\rebuild_memory.py recall `
  --database D:\PRIVATE\memory_jazn.sqlite3 `
  --from 2025-01-01T00:00:00+00:00 `
  --to 2026-12-31T23:59:59+00:00 `
  "latarnia ze spaceru"
```

## L3, aktywacja i prywatna pamięć

Tabela `memory_activation_guard` powstaje w stanie fail-closed:

- `automatic_l2 = 0`;
- `automatic_l3 = 0`;
- `automatic_activation = 0`;
- `private_replacement_allowed = 0`.

Narzędzie nie ma polecenia automatycznej aktywacji ani zastąpienia prywatnej
pamięci. Nawet ręczne zezwolenie na zastąpienie wymaga trwałego SHA-256 raportu
benchmarku. Sam test syntetyczny, integralność SQLite, licznik rekordów lub
poprawny FTS5 nie są dowodem rzeczywistego recall.

Prywatna pamięć może zostać zastąpiona dopiero po oddzielnym, rzeczywistym
benchmarku obejmującym co najmniej:

- recall na prywatnych przypadkach oczekiwanych;
- trafność rozmowy i czasu;
- poprawną proweniencję każdego zaakceptowanego trafienia;
- zachowanie „nie wiem” dla przypadków negatywnych;
- ciągłość po restarcie;
- jawną decyzję operatora.

Ta przebudowa nie wykonuje takiego benchmarku i nie zmienia aktywnej prywatnej
bazy.

## Ustawienia

Przykład pliku JSON:

```json
{
  "require_fts5": true,
  "embeddings_enabled": false,
  "embedding_model": null,
  "retrieval_limit": 20,
  "min_lexical_score": 0.0,
  "require_provenance": true,
  "automatic_l2": false,
  "automatic_l3": false,
  "automatic_activation": false
}
```

Plik można przekazać przez `--settings` przed nazwą podpolecenia albo przez
`JAZN_MEMORY_REBUILD_SETTINGS`.

## Źródła projektowe

Architektura opiera się na dokumentacji i publikacjach źródłowych:

- [Python `typing.Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol) — strukturalny, typowany kontrakt adapterów;
- [SQLite FTS5](https://sqlite.org/fts5.html) — wymagany indeks pełnotekstowy, `MATCH`, ranking i kontrola integralności;
- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) — oddzielenie pamięci parametrycznej od jawnej pamięci zewnętrznej i znaczenie proweniencji;
- [Sentence Transformers: Semantic Search](https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html) — opcjonalne wyszukiwanie wektorowe i retrieve/rerank.

Nie trenowano ani nie dostrajano modelu LLM w ramach tej zmiany. Najpierw
utrzymywany jest audytowalny baseline FTS5, a embeddingi pozostają opcjonalnym,
mierzalnym rozszerzeniem.
