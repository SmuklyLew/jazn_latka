# Jaźń v16.3.14 — Memory Rebuild Test00 + mierzalny Recall

## Cel

Przed dalszą rozbudową pełnego importera pamięci zamrażamy dwa kontrakty:

1. `TEST 00 -> 01 -> 02 -> 03 -> 04 -> FINAL` jako kolejne, mierzalne etapy odbudowy;
2. Recall jako osobny subsystem rozwijany kolejno: **źródła -> benchmark -> FTS5 baseline -> eksperymenty A/B -> dopiero ewentualny trening/wybór retrievera**.

Ta zmiana nie trenuje modelu, nie aktywuje pamięci i nie promuje rekordów do L2/L3.

## Stała zasada „source gate przed kodem”

Przed rozpoczęciem każdej kolejnej fazy implementacyjnej trzeba:

1. spisać invariants i oczekiwane failure modes;
2. sprawdzić, czy obecny kod/repo nie ma już kanonicznej implementacji;
3. potwierdzić projekt w źródłach pierwotnych lub oficjalnej dokumentacji;
4. dopiero potem pisać kod;
5. dodać test regresyjny dla znalezionych ograniczeń;
6. nie przechodzić do następnej fazy przy czerwonym CI.

Preferowane źródła: dokumentacja SQLite/Python/prompt_toolkit, publikacje ACL/EMNLP/NeurIPS/arXiv autorów benchmarków i oficjalne dokumentacje bibliotek. Blog lub wynik wyszukiwarki nie jest wystarczającym dowodem, jeśli dostępne jest źródło pierwotne.

## TEST 00 — Source Fidelity / bezstratny odczyt

### Cel

Udowodnić, że źródło można zachować bajtowo oraz zinterpretować bez utraty obserwowanych struktur. Test00 jest kontrolną bazą źródłową, nie pamięcią autobiograficzną.

### Wejścia

- `conversations*.json`;
- pełne `chat.html`;
- samodzielne `chatGPT-export-manual-*.html`;
- ZIP eksportu ChatGPT;
- sidecary JSON, np. feedback/shared/user, jako osobne źródła.

### Source mirror

Wynik domyślnie trafia do:

```text
memory/rebuild_tests/test_00/<run-id>/
  source_mirror.sqlite3
  summary.private.json
  summary.sanitized.json
```

`source_mirror.sqlite3` nie używa jednego BLOB-u na cały plik. Oficjalny SQLite ma domyślny `SQLITE_MAX_LENGTH=1,000,000,000`, a rzeczywiste eksporty mogą przekraczać 1 GB. Surowe źródło jest więc dzielone na numerowane fragmenty po 8 MiB:

```text
source_mirror_sources
source_mirror_chunks
source_mirror_roles
source_mirror_content_types
source_mirror_zip_members
```

Każdy chunk ma SHA-256. Po zapisie całe źródło jest logicznie rekonstruowane w kolejności chunków i ponownie hashowane. Warunek wierności:

```text
SHA256(original stream) == SHA256(reconstructed chunks)
```

Dla ZIP każdy członek jest dodatkowo odczytany do końca i otrzymuje własny SHA-256 oraz metadata CRC/rozmiaru.

### Parse fidelity

Dla rozmów liczymy niezależnie z raw `mapping` i z `ConversationGraph`:

- liczbę nodes;
- liczbę messages;
- branch points;
- wszystkie obserwowane `author.role`;
- wszystkie obserwowane `content_type`.

Nie ma allowlisty ról. Nieznana rola jest zachowana i raportowana. `user`, `assistant`, `system`, `tool` są zwykłymi obserwowanymi wartościami, nie jedynymi dozwolonymi wartościami.

### Wyniki

- `PASSED` — raw round-trip i strukturalne porównania są bezstratne;
- `LOSSY` — bajty zachowano, ale parser musiał użyć np. rendered HTML fallback;
- `BLOCKED` — źródło jest zachowane, ale format nie ma obsługi interpretacyjnej wymaganej dla testu;
- `FAILED` — błąd integralności, parse fidelity lub round-trip.

Rendered HTML fallback nigdy nie może być `PASSED`, ponieważ syntetyzuje role i nie ma pełnego grafu/timestampów.

### Granica prawdy

Test00 nie dowodzi, że treść źródła jest prawdziwym wspomnieniem, nie ustala `memory_eligible`, nie tworzy L1/L2/L3 i nie jest dowodem aktywnej Jaźni.

## TEST 01 — Kanoniczne, bezstratne L0

Wejście: źródła dopuszczone przez Test00.

Fazy:

```text
freeze inventory -> plan -> build L0 -> verify provenance -> read-only validation
```

Wymagania:

- pełne grafy i branche;
- raw payload/revisions/assets;
- sidecary i embedded documents z proweniencją;
- dziennik/source records;
- FTS/FK/integrity;
- zero automatycznej akceptacji doświadczeń i L2/L3.

## TEST 02 — Normalizacja i projekcje

Surowe L0 pozostaje niezmienne. Każda klasyfikacja jest pochodną z linkiem do źródła.

Sprawdzane obszary:

- visible / hidden / non-dialogue;
- role i klasy techniczne/tool;
- sensitivity;
- memory eligibility;
- timestamp status;
- indeksowanie FTS;
- raw <-> normalized reconciliation.

## TEST 03 — Pełny rebuild integracyjny

```text
dry-run -> fresh memory_jazn.sqlite3 -> dedupe/merge -> JSON<->HTML -> reconciliation -> verify
```

Relacje źródeł muszą rozróżniać `identical/subset/extends/divergent`. Porównanie z Test00/01/02 nie może opierać się wyłącznie na licznikach lub PK — wymagane są stabilne hashe treści i jawne konflikty.

## TEST 04 — Prywatna akceptacja pełnej bazy

Wymaga wszystkich znanych źródeł i najświeższego eksportu z atestacją operatora.

Fazy:

```text
fresh build A
-> same-target idempotence
-> fresh build B
-> reproducibility
-> Test03 reconciliation
-> real private Recall benchmark
-> manual multi-turn
-> optional restart continuity
```

Sukces developerski pozostaje `developer_test04_passed`; nie oznacza aktywacji ani zgody L3.

## FINAL — Freeze pełnej pamięci bazowej

Wymaga zaliczonego Test04. Tworzy spójny snapshot SQLite przez Backup API i finalne manifesty/raporty. Wynik jest wejściem do osobnego `Verified Memory Restore`.

## Recall — osobny subsystem

### R0 — Source Fidelity

Test00 musi być poprawny przed oceną retrievera. Benchmark na niekompletnym L0 byłby niewiarygodny.

### R1 — Benchmark schema

Kategorie przypadków:

- direct;
- paraphrase;
- explicit_recall;
- implicit_recall;
- referential_followup;
- temporal;
- multi_session;
- update;
- conflict;
- negative;
- provenance;
- role_boundary;
- sensitive_boundary;
- implicit_constraint.

Prywatne zapytania i trafienia mogą istnieć wyłącznie w private report. Sanitized report przechowuje hashe, liczniki i metryki.

### R2 — FTS5/BM25 baseline

Aktualna implementacja `fts5-bm25/v1`:

- używa `TypedMemoryAPI`;
- tylko L0;
- wymaga provenance;
- `use_embeddings=False`;
- nie ma modelu treningowego;
- mierzy latency i jakość.

Metryki:

- case accuracy / Recall@1,3,5,10,20;
- MRR;
- nDCG;
- abstention accuracy;
- false-memory rate;
- provenance accuracy;
- temporal accuracy;
- sensitive leakage count/rate;
- wyniki per kategoria.

Safety invariants, np. credential leakage, muszą mieć próg zero. Progi jakości retrieval ustalamy na rzeczywistym baseline, a nie arbitralnie przed pomiarem.

### R3 — Query rewrite A/B

Dopiero po ustaleniu stabilnego baseline. CONQRR uzasadnia kontekstowe przepisywanie zapytań do standalone query, ale nowa ścieżka musi być mierzona A/B na tym samym benchmarku i zachować możliwość powrotu do raw query.

### R4 — Dense retrieval / reranker A/B

Embedding/re-ranker nie zastępuje baseline. Kandydat może wejść dalej tylko jeśli poprawia uzgodnione metryki bez regresji abstention, provenance, temporal i safety.

### R5 — Trening / wybór retrievera

**Nieimplementowane w v16.3.14.**

Trening jest dozwolony dopiero po:

1. pełnym Test00-03;
2. zamrożonym prywatnym benchmarku;
3. FTS5 baseline;
4. A/B prostszych metod;
5. audycie false-negative/hard-negative;
6. osobnej decyzji o modelu i danych treningowych.

## Źródła techniczne

- SQLite Online Backup API: https://www.sqlite.org/backup.html
- SQLite limits / `SQLITE_MAX_LENGTH`: https://www.sqlite.org/limits.html
- SQLite FTS5 / BM25: https://www.sqlite.org/fts5.html
- Python `sqlite3`: https://docs.python.org/3/library/sqlite3.html
- prompt_toolkit full-screen applications: https://python-prompt-toolkit.readthedocs.io/en/stable/pages/full_screen_apps.html
- LongMemEval: https://arxiv.org/abs/2410.10813
- LoCoMo: https://aclanthology.org/2024.acl-long.747/
- CONQRR: https://aclanthology.org/2022.emnlp-main.679/
- BEIR: https://arxiv.org/abs/2104.08663

## Granice repozytorium

- `memory/`, `workspace_runtime/`, SQLite/WAL/SHM i prywatne eksporty nie mogą trafić do Git;
- kod Test00 tworzy artefakty wyłącznie lokalnie;
- żadna faza tego PR nie uruchamia automatycznej promocji L2/L3;
- prywatne benchmarki Recall nie trafiają do repozytorium;
- zielone CI nie zastępuje prywatnego Test04.
