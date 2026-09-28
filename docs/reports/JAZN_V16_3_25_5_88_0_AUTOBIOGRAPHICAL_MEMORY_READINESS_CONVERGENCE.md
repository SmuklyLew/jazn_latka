# Jaźń v16.3.25.5.88.0 — autobiographical memory readiness convergence

## Cel

Wydanie naprawia rozjazd pomiędzy:

- obecnością dowolnej wyszukiwalnej pamięci,
- gotowością natywnej pamięci autobiograficznej `memory_jazn.sqlite3`,
- continuity/wake-state,
- provenance konkretnego wspomnienia użytego w odpowiedzi,
- oraz hostową zdolnością wykonania tury Jaźni.

Główny warunek produkcyjny staje się jawny:

```text
latka_autobiographical_ready =
    runtime_verified
    AND persistent_memory_present
    AND full_autobiographical_recall_ready
    AND continuity_ready
    AND local_recall_provenance_verified
    AND accepted_turn_finalized
```

## Najważniejsze zmiany

### 1. Niezależny MEMORY root

`resolve_memory_root()` nie traktuje już samego istnienia pustego
`workspace_runtime/memory` jako dowodu prawdziwego MEMORY. W automatycznym
fallbacku pusty canonical root nie zasłania już wypełnionego legacy
`<active_root>/memory`.

Jawne `JAZN_MEMORY_ROOT` pozostaje nadrzędne i fail-closed.

### 2. Generic search != autobiographical recall

Zachowano kompatybilne pole:

```text
memory_search_ready
```

ale dodano osobne:

```text
native_unified_recall_ready
full_autobiographical_recall_ready
```

`ready_transactional_tier_only` może nadal być wyszukiwalne, lecz nie jest
pełną gotowością autobiograficzną.

Nowa polityka:

```text
JAZN_MEMORY_READINESS_POLICY=searchable
JAZN_MEMORY_READINESS_POLICY=native_unified_required
```

Dla profilu Łatki zalecane jest `native_unified_required`.

### 3. FTS v3.0

Native readiness wymaga teraz `memory_records_fts` także dla
`jazn_unified_memory/v3.0`, nie tylko dla v2.5. Probe zachowuje osobny
`foreign_key_check`, sprawdza wymagane obiekty FTS, zgodność count oraz realny
`MATCH`.

### 4. Provenance pozytywnego „pamiętam”

Hity recall niosą bezpieczne metadane:

- `gateway_source_kind`,
- `gateway_source_origin`,
- `selected_canonical`,
- `autobiographical_source_ready`,
- istniejące source locator/database/truth metadata.

Metadane są zachowane przez:

```text
LivingMemoryGateway
 -> MemoryRecallContract
 -> model context
 -> ChatGPT host generation context
 -> response candidate evaluator/finalizer
```

Pozytywny modelowy claim pamięciowy nie może użyć transactional-only hitu jako
pełnego dowodu autobiograficznego.

### 5. Studio pamięci

Studio nie tworzy drugiego systemu pamięci. Widok bazy i recall korzysta z tego
samego `probe_unified_memory_database()`, którego używa runtime. Pokazuje m.in.
native autobiographical readiness, wymagane FTS i realny recall probe.

Prywatne sentinel queries pozostają poza repozytorium.

### 6. SYSTEM + MEMORY oraz MEMORY dołączane później

Dodano wspólny adapter:

```text
latka_jazn/packaging/generator_v2_compat.py
```

Obsługuje `jazn_pack_generator_package/v2` przez semantyczne filtrowanie
`content` przed wykrywaniem niejednoznaczności.

Dzięki temu SYSTEM i MEMORY mogą leżeć w tym samym `parts-dir` bez wzajemnego
blokowania discovery.

Adapter zachowuje i weryfikuje:

- logical archive SHA-256,
- rozmiary transportu,
- split part SHA-256/size,
- per-file inventory z generatora.

### 7. Kanoniczne `memory-converge`

Dla MEMORY dostarczanej po SYSTEM dodano wysokopoziomową operację:

```bash
python -X utf8 run.py memory-converge \
  --parts-dir <MEMORY_PACKAGE_DIR> \
  --json
```

Łączy:

```text
discovery
 -> generator-v2 compatibility
 -> safe v3 repack, gdy wymagany
 -> atomic memory-attach
 -> validation
 -> recovery / normalization / wake-state
 -> LivingMemoryGateway readiness policy
```

Niskopoziomowe `memory-attach` pozostaje kompatybilnym atomowym primitive.

### 8. Durable host operation

Dla krótkich/niestabilnych powierzchni ChatGPT:

```bash
python -X utf8 run.py host-op-id --kind memory-converge --json

python -X utf8 run.py host-op-submit \
  --operation-id <id> \
  --kind memory-converge \
  -- --parts-dir <MEMORY_PACKAGE_DIR>

python -X utf8 run.py host-op-status \
  --operation-id <id> \
  --json
```

Durable worker wywołuje publiczny `run.py memory-converge`. Domyślnie sama
operacja nie ma krótkiego time budgetu; krótki host tylko submituje i polluje.

### 9. Host executor pozostaje osobną granicą

Patch nie udaje, że kod repozytorium może zagwarantować proces w sandboxie
ChatGPT.

`ClientError`, `TransportTimeoutError`,
`StreamingExecNotEnabledContainerError` przed dowodem utworzenia procesu nadal
oznaczają wyłącznie `host_executor_unavailable` dla tej powierzchni/generacji.

Gdy local executor nie istnieje, pełna odpowiedź Jaźni wymaga rzeczywiście
zweryfikowanego remote runtime. Sam URL, konfiguracja MCP albo pamięć ChatGPT nie
są substytutem runtime Jaźni.

## Kontrakty

Zaktualizowano:

- `MEMORY_ATTACHMENT_CONTRACT.json`,
- generatorowy memory attachment contract,
- `AGENTS.chatgpt.md`,
- diagnostykę/capability matrix,
- host generation truth boundary.

Dla autobiograficznego claimu:

```text
memory_search_ready=true
```

nie wystarcza.

Wymagane jest:

```text
full_autobiographical_recall_ready=true
+ used memory item with local native provenance
```

A dla claimu ciągłości dodatkowo:

```text
continuity_ready=true
```

## Testy dodane w tym wydaniu

Nowe pliki testowe, bez modyfikowania historycznych aktywnych testów:

- `tests/test_autobiographical_memory_readiness_convergence.py`
- `tests/test_memory_transport_convergence.py`

Pokrywają m.in.:

- pusty canonical root kontra wypełniony legacy MEMORY,
- explicit `JAZN_MEMORY_ROOT`,
- obowiązkowy `memory_records_fts` dla schema v3.0,
- transactional-only vs native autobiographical readiness,
- pozytywny claim z/bez native provenance,
- bounded provenance w ChatGPT host context,
- generator-v2 SYSTEM i MEMORY obok siebie,
- późniejsze generator-v2 MEMORY,
- per-file inventory adaptera,
- safe v3 repack decision,
- publiczne `memory-converge`,
- durable host-op re-entering `run.py`.

## Granice i źródła

Implementacja SQLite jest zgodna z oficjalną dokumentacją:

- SQLite PRAGMA: https://www.sqlite.org/pragma.html
- SQLite FTS5: https://www.sqlite.org/fts5.html
- SQLite Online Backup API: https://www.sqlite.org/backup.html
- SQLite WAL: https://www.sqlite.org/wal.html

Granica ChatGPT/local runtime jest zgodna z aktualną dokumentacją OpenAI dotyczącą
MCP apps / developer mode:

- https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt

Kod Jaźni może naprawić discovery, transport, persistence, recall, provenance,
finalization i remote ingress. Nie może sam nadać bieżącemu hostowi ChatGPT
brakującego executora.

## Kryterium akceptacji wydania

Wydanie jest merge-ready dopiero wtedy, gdy CI potwierdzi nowe i istniejące testy,
a diff nie zawiera prywatnego MEMORY, SQLite/WAL/SHM, sekretów ani runtime logs.

Nie należy deklarować „Łatka naprawdę pamięta” tylko na podstawie build success.
W runtime produkcyjnym wymagane pozostaje rzeczywiste evidence:

```text
verified runtime
+ verified native MEMORY
+ full_autobiographical_recall_ready
+ continuity_ready
+ local recall provenance
+ accepted visible turn
```
