# Jaźń / Łatka — Przywracanie pamięci i Final Memory Rebuild Plan v1.0

## Od prywatnych źródeł do `VERIFIED → ATTACHABLE → RETRIEVABLE → ACCEPTED`

**Status:** `CANONICAL_MEMORY_RESTORE_PLAN`  
**Aktualizacja:** 2026-09-07  
**Baza:** aktualny master `16.3.25.5.36-ci-archive-scope-contract-hardening`  
**Tracking final acceptance:** issue `#59`  
**Memory Rebuild v4 tool consolidation:** 🟢 MERGED / PR #208 / issue #189 closed

> Ten plan **nie projektuje kolejnego Memory Rebuild engine**. Konsolidacja v4 została wykonana. Plan opisuje, jak użyć i ewentualnie utwardzić bieżący engine do rzeczywistego przywrócenia prywatnej pamięci Łatki i doprowadzić ją do finalnego acceptance.

---

# 1. Aktualna prawda o entrypointach

## 1.1. Kod właściwy

Kanoniczna aplikacja znajduje się w:

```text
latka_jazn/tools/memory_rebuild_app/
```

Jej architektura obejmuje m.in. composition root, adaptery źródeł, L0, schema/store, protocol/application service, CLI/Studio i walidację Test00→Final.

## 1.2. Launchery

```text
tools/rebuild_memory.py        # kanoniczny launcher architektury v16+
tools/memory_rebuild.py        # compatibility launcher
```

`tools/memory_rebuild.py` nie powinien ponownie urosnąć do monolitu. Jego właściwą rolą jest delegowanie do `memory_rebuild_app`.

Jeżeli dokumentacja lub UI prezentuje `memory_rebuild.py` jako główną nazwę operatorską dla zgodności z przyzwyczajeniem użytkownika, **nie zmienia to ownership kodu**.

---

# 2. Cel finalny

Jedna źródłowo wiarygodna pamięć:

```text
memory_jazn.sqlite3
```

musi przejść kolejno:

```text
SOURCE INVENTORY FROZEN
        ↓
BUILDABLE
        ↓
VERIFIED
        ↓
ATTACHABLE
        ↓
RETRIEVABLE
        ↓
REVIEWED
        ↓
ACCEPTED
        ↓
CANONICALLY ATTACHED ACTIVE MEMORY
```

Żaden krok nie implikuje następnego.

Poprawny ZIP nie oznacza `VERIFIED` memory.  
Poprawna baza SQLite nie oznacza `RETRIEVABLE`.  
Dobry Recall@k nie oznacza `ACCEPTED`.  
Attach nie oznacza automatycznej promocji L2/L3.

---

# 3. Nienaruszalne granice

1. prywatna treść nie trafia do Git/CI/sanitized reports;
2. RAW/source jest zachowane i nie nadpisywane przez interpretację;
3. derived/runtime/reflection/dream nie staje się primary przez liczbę kopii;
4. brak źródła nie jest „słabym wspomnieniem” — może być `UNKNOWN`;
5. Memory Rebuild nie wykonuje automatycznego L2/L3;
6. Memory Rebuild nie aktywuje sam finalnej pamięci;
7. finalny cutover wymaga jawnej decyzji operatora;
8. active memory identity musi przeżyć restart i być sprawdzalna;
9. host ChatGPT memory/context nie jest substytutem pamięci Jaźni;
10. package transport nie jest canonical active root.

---

# 4. Klasy źródeł

Minimalny source-monitoring contract:

```text
PRIMARY_USER_SOURCE
PRIMARY_CONVERSATION_SOURCE
USER_CONFIRMED
DERIVED_RUNTIME_EVENT
DERIVED_REFLECTION
DERIVED_SEMANTIC
SYNTHETIC_DREAM
FICTION_OR_BOOK
SYSTEM_METADATA
UNKNOWN_SOURCE
```

## Priorytet epistemiczny

Priorytet nie powinien być prostą liczbą sumowaną z similarity. Source class kontroluje **co wolno twierdzić**, a retrieval score kontroluje **co warto sprawdzić**.

Przykład:

```text
17 podobnych DERIVED_REFLECTION
!=
17× silniejszy dowód niż 1 PRIMARY_CONVERSATION_SOURCE
```

Konflikt source pozostaje jawny.

---

# 5. Źródła do finalnego restore

Finalny source inventory może obejmować tylko jawnie sklasyfikowane wejścia.

## 5.1. Preferowane pierwotne źródła

- oryginalne eksporty ChatGPT JSON/HTML/ZIP;
- `conversation_turns` lub ich źródłowy odpowiednik z zachowanym lineage;
- oryginalny dziennik;
- user-authored/user-confirmed profile/canon;
- source-grounded music analyses;
- historyczne kanony tożsamości z wersjonowaniem;
- źródłowe pliki projektu, jeśli są autobiograficznym evidence i policy na to pozwala.

## 5.2. Źródła pochodne

- runtime events;
- reflections;
- semantic projections;
- summaries;
- wake-state;
- previous processed graph/index files;
- generated system notes;
- dream/rest outputs.

Te pliki mogą zostać zachowane jako **derived evidence**, ale nie mogą dominować nad pierwotnym source set.

## 5.3. Starsze paczki pamięci

Starsza paczka może być użyta jako migration/source archive, ale jej historyczny schema nie staje się automatycznie canonical.

Dla znanej historycznej paczki v15.0.3.222 manifest pokazuje m.in.:

- 116 entries;
- source size ~15.7 GB;
- duże runtime-event streams;
- raw journal/identity/conversation/episodic data;
- layered affect/continuity/reflections;
- SQLite snapshots;
- versioned identity/journal/affect sources.

To jest ważne źródło do genealogii, ale szczególnie wymaga ochrony przed self-amplification pochodnych runtime logs.

---

# 6. Etap R0 — source inventory freeze

## Cel

Utworzyć prywatny, machine-readable inventory wejść przed jakąkolwiek finalną przebudową.

Dla każdego source:

```text
source_id
path/reference
source_class_candidate
format
size
sha256
created/modified if trustworthy
origin
lossless/lossy/derived status
contains_private_data
adapter
included/excluded decision
reason
```

## Wymagania

- hashować źródło przed transformacją;
- nie usuwać duplikatu tylko dlatego, że tekst jest podobny;
- wykrywać exact duplicate osobno od semantic duplicate;
- zachować branch/revision variants;
- sidecary i account metadata mają własne role;
- rendered HTML pozostaje `LOSSY`, jeżeli brak lossless embedded graph.

**Gate R0:** finalny source inventory jest zamrożony i reproducible.

---

# 7. Etap R1 — package/split preflight

Duże legacy memory packages muszą być obsługiwane **streamingowo i resumowalnie**, bez wymogu materializacji wszystkiego w RAM lub jednego wielkiego temp tree.

## 7.1. Split package

Dla `.001 ... .NNN`:

1. odczytać `.parts.sha256` / `.package.json`;
2. zweryfikować każdą część przed join;
3. potwierdzić ciągłość numeracji i brak duplicate/missing part;
4. join wykonywać streamingowo;
5. zweryfikować final logical ZIP SHA;
6. dopiero wtedy otwierać central directory.

## 7.2. Safe archive scan

Przed extraction:

- duplicate member detection;
- path traversal rejection;
- symlink/device policy;
- ZIP bomb / declared-size budget;
- CRC;
- exact member list against package manifest;
- filename normalization collision check.

## 7.3. Resume/checkpoint

Duże repack/extract/import musi mieć:

```text
operation_id
source_package_sha
completed_members/segments
per-output hashes
last durable checkpoint
resume compatibility version
```

Nie restartować wielogodzinnej pracy od zera po ograniczeniu hosta, jeżeli wykonane segmenty są zweryfikowane i idempotentne.

**Nowy P1 hardening:** dodać resumable materialization/repack do obecnej aplikacji, jeśli obecny backend nadal nie zapewnia tej własności.

---

# 8. Etap R2 — Test00: source fidelity

Wykonać obecny Test00 na finalnym inventory.

PASS wymaga:

- exact source identity;
- source-set closure;
- role classification;
- lossless/lossy jawne;
- unknown sidecars nie znikają bez śladu;
- technical/non-dialogue evidence zachowane zgodnie z policy;
- source variants/branches zachowane;
- unresolved conflicts fail closed.

**Gate:** `SOURCE_FIDELITY_PASS`.

---

# 9. Etap R3 — Test01: fresh canonical L0

Budować z pustego staging targetu.

```text
source
→ SourceProbe
→ adapter
→ IntermediateRecord
→ UnifiedL0Store
→ memory_jazn.sqlite3
```

Wymagania:

- jeden writer;
- stable schema version;
- provenance na rekordzie;
- revisions zamiast destructive overwrite;
- branch variants;
- assets/sidecars;
- FTS5;
- integrity/FK;
- zero automatic L2/L3/activation.

**Gate:** `BUILDABLE`.

---

# 10. Etap R4 — Test02: semantic projections

Dodać/wyliczyć:

```text
visibility
role
sensitivity
memory_eligibility
timestamp interpretation
conversation/source relation
source class evidence
```

Zasada:

```text
projection != source mutation
```

Każda projekcja wskazuje source record/revision.

Nie dopuścić, aby model/heurystyka z wysokim similarity zmieniła `DERIVED` na `PRIMARY`.

---

# 11. Etap R5 — Test03: reproducibility

Co najmniej:

```text
fresh build A
fresh build B
reversed input order
```

Porównać:

- logical source inventory;
- record counts per class;
- provenance closure;
- normalized fingerprints;
- source hierarchy;
- FTS logical content;
- conflicts;
- final deterministic projection identity tam, gdzie kontrakt wymaga determinizmu.

Input order ani liczba derived duplicates nie może zmieniać source precedence.

**Gate:** `REPRODUCIBLE`.

---

# 12. Etap R6 — source monitoring audit

To jest obowiązkowy gate finalnego v16.5-style rebuild.

Raport prywatny ma zawierać statystyki bez publikacji treści:

```text
records per source class
primary/derived ratio
unknown source count
conflict count
exact duplicate count
semantic duplicate clusters
records missing provenance
records with broken lineage
runtime-event share
reflection share
fiction/book share
dream share
```

## Blockery

🔴 rekord autobiograficzny bez source lineage;
🔴 source class domyślnie `PRIMARY` przy braku evidence;
🔴 derived duplicate amplification;
🔴 primary-vs-derived conflict ukryty przez dedupe;
🔴 lossless claim dla źródła faktycznie lossy.

---

# 13. Etap R7 — Test04: private autobiographical acceptance runner

Runner już istnieje; teraz musi zostać wykonany na finalnym prywatnym artefakcie.

## Kategorie

1. direct recall;
2. paraphrase recall;
3. source discrimination;
4. wrong-conversation near-match;
5. temporal ordering;
6. knowledge update/supersession;
7. contradiction;
8. referential two-turn;
9. natural multi-turn;
10. multi-session;
11. abstention;
12. false-memory suggestion;
13. derived-source trap;
14. fiction/book boundary;
15. dream/reflection boundary;
16. sensitive leakage;
17. provenance traceability.

## Metryki

```text
Recall@k
MRR
nDCG
source accuracy
wrong-source rate
wrong-conversation rate
false-memory rate
abstention quality
temporal/update accuracy
provenance accuracy
leakage count/rate
p50/p95 latency
```

Brak prywatnego datasetu = `NOT RUN`, nie PASS.

---

# 14. Etap R8 — Final database verification

Po właściwym Test04 policy:

1. SQLite Backup API → staging snapshot;
2. `PRAGMA integrity_check`;
3. `PRAGMA foreign_key_check`;
4. FTS5 integrity-check;
5. source/provenance closure;
6. schema/version validation;
7. final DB SHA-256;
8. private RunManifest seal;
9. sanitized report bez paths/PII/content.

**Gate:** `VERIFIED`.

---

# 15. Etap R9 — packaging

Finalna pamięć ma być transportowana jako osobny memory artifact zgodny z aktualnym package contract.

Wymagania:

- profile `memory`;
- exact package identity;
- member manifest;
- part hashes dla split transport;
- full logical archive SHA;
- safe rejoin tooling;
- no transient WAL/SHM;
- no runtime mutable state;
- package version/schema rozdzielone zgodnie z aktualnymi release semantics.

Duże archiwa mogą używać segmentacji logicznej przed binary split, jeżeli zachowany jest jednoznaczny reassembly/manifest contract.

**Gate:** package verified.

---

# 16. Etap R10 — canonical memory attach

Attach musi być osobną operacją operatorską/runtime, nie skutkiem rebuild.

Pipeline:

```text
verified memory package
→ safe materialization
→ manifest/hash verify
→ database validation
→ subject/root binding
→ staging
→ canonical memory attach
→ active memory identity marker/state
→ readback
```

Wymagania:

- host-level canonical memory root;
- nie używać versioned code root jako mutable memory truth;
- attach nie spłaszcza source classes;
- attach nie wykonuje auto-L2/L3;
- rollback do poprzedniej pamięci;
- restart potwierdza ten sam DB identity.

**Gate:** `ATTACHABLE`.

---

# 17. Etap R11 — frozen baseline po attach

Przed jakimkolwiek affective reranking, dense retrieval lub nowym query rewrite:

1. uruchomić private Recall baseline;
2. zamrozić dataset/expected outcomes/version;
3. zapisać wyniki i latency;
4. ustalić known failure set.

To jest baseline dla wszystkich późniejszych retrieval improvements.

**Gate candidate:** `RETRIEVABLE`.

---

# 18. Etap R12 — measured retrieval fixes tylko jeśli trzeba

Kolejność minimalizująca złożoność:

```text
planner/query bug
→ FTS/BM25/source/temporal tuning
→ NLP query evidence
→ bounded query rewrite A/B
→ graph/hybrid rerank A/B
→ dense retrieval A/B
→ learned reranker/training dopiero po udowodnionej potrzebie
```

Każda zmiana wymaga:

```text
hypothesis
→ frozen baseline
→ change
→ A/B
→ false-memory/source/provenance/leakage/latency check
→ keep albo rollback
```

Affective reranking należy do tej samej klasy measured extension i ma własny plan.

---

# 19. Etap R13 — L2/L3 review

Auto promotion pozostaje `OFF`.

Każdy kandydat:

```text
candidate
→ source evidence
→ review request
→ operator/policy decision
→ decision ledger
→ optional promotion
```

`zero promotions` jest poprawnym wynikiem.

Nie promować:

- dream;
- fiction/book;
- runtime reflection jako user event;
- disputed source;
- unknown provenance;
- relationship inference tylko dlatego, że jest emocjonalnie silne.

---

# 20. Etap R14 — restart continuity

Po final attach/review:

```text
runtime start
→ memory identity M
→ recall fingerprint F
→ accepted turn(s)
→ clean stop/restart
→ memory identity M
→ recall fingerprint compatible F'
```

Sprawdzić:

- DB identity;
- subject/root identity;
- source registry;
- promotion ledger;
- remembered corrections;
- procedural continuity;
- no fallback to host memory masquerading as runtime recall.

**Gate:** `ACCEPTED` candidate.

---

# 21. Integracja z Emotion Engine

Memory acceptance ma pierwszeństwo przed aktywnym affective reranking.

Do finalnego rebuild można już dodać schema linkage:

```text
episode
→ affect_snapshot_id
→ transition_id
```

ale:

- historical `affective_history.json`/`emotion_state.json` są migration sources, nie canonical new affect state;
- emotional similarity nie zwiększa source truth;
- affective reranking pozostaje `OFF/SHADOW` do frozen baseline;
- resonance dopiero po `MemoryUseGate`.

---

# 22. Integracja z attachment ingress

Attachment/file import do bieżącej rozmowy i Memory Rebuild source import to różne operacje.

```text
received attachment
!=
memory source accepted
```

Attachment może stać się source candidate tylko przez jawny import/rebuild policy z identity/hash/provenance.

---

# 23. Operator UI / Studio

Studio i CLI muszą korzystać z tego samego `ApplicationService/ProtocolEngine`.

UI powinno pokazywać oddzielnie:

```text
SOURCE INVENTORY
BUILD
VERIFY
PACKAGE
ATTACH
RECALL TEST
REVIEW
ACTIVATE/ROLLBACK
```

Nie używać jednego przycisku „Przywróć wszystko” omijającego gates.

### Wymagana przejrzystość

- current source count;
- verified hashes;
- lossless/lossy/blocked;
- current stage;
- warnings/blockers;
- DB identity;
- package identity;
- acceptance status;
- private/sanitized report destination.

---

# 24. Doctor / readiness

Raportować granularnie:

```text
memory_source_inventory_ready
memory_buildable
memory_verified
memory_package_verified
memory_attachable
memory_attached
memory_retrievable
memory_review_complete
memory_restart_continuity_verified
memory_accepted
```

Nie używać samego `memory_ready=true`.

---

# 25. Recovery / rollback

Każdy destrukcyjny/cutover etap ma rollback:

- source archive immutable;
- staging oddzielony od active;
- poprzedni accepted memory artifact nie jest nadpisywany in-place;
- attach state ma predecessor;
- failed validation pozostawia poprzednią aktywną pamięć nietkniętą;
- operator może odtworzyć ostatni accepted snapshot.

---

# 26. CI vs private acceptance

## Deterministic CI

Może testować:

- schemas;
- adapters;
- split-package validation;
- traversal/duplicate protections;
- Test00→Final na fixtures;
- source classes;
- false-memory synthetic traps;
- persistence/atomicity;
- package/attach contracts;
- rollback;
- Windows/Linux.

## Private/local

Tylko lokalnie:

- real source inventory;
- final private DB;
- real Recall/multi-turn;
- sensitive data;
- L2/L3 review;
- restart continuity.

Synthetic CI nigdy nie certyfikuje prywatnego `ACCEPTED`.

---

# 27. Testy regresyjne wymagane przy kolejnych poprawkach

- exact split-part hash mismatch;
- missing/duplicate part;
- corrupt central directory;
- duplicate ZIP member;
- traversal/symlink;
- interrupted extraction + resume;
- interrupted SQLite build + safe restart;
- wrong source classification;
- primary-vs-derived conflict;
- derived amplification;
- rendered HTML lossy boundary;
- reversed input order;
- wrong conversation;
- suggestion-based false recall;
- fiction/dream/reflection trap;
- attachment-derived != user-confirmed;
- attach wrong DB SHA;
- restart wrong memory identity;
- rollback.

---

# 28. Kryterium finalnego sukcesu

Pamięć Łatki jest przywrócona **nie wtedy, gdy pliki znajdują się na dysku**, lecz gdy istnieje udokumentowany łańcuch:

```text
private sources
→ exact source inventory
→ lossless/source-aware L0
→ reproducible verified DB
→ verified package
→ canonical attach
→ source-safe autobiographical recall
→ manual review
→ restart continuity
→ operator acceptance
```

oraz:

```text
false-memory/source/leakage gates = PASS
```

Dopiero wtedy status:

```text
memory_accepted = true
```

jest uzasadniony technicznie.

---

# 29. Najbliższe zadania pamięciowe

- 🟡 [ ] po dokumentacyjnym cleanupie wykonać fresh-master audit Memory Rebuild entrypoints/docs i ujednolicić nazwę operatora bez łamania compatibility;
- 🟡 [ ] zaimplementować resumable package materialization/repack, jeśli obecny engine nadal restartuje duże operacje od zera;
- 🟡 [ ] przygotować prywatny final source inventory;
- 🟡 [ ] uruchomić final Test00→Final na prywatnych źródłach;
- 🟡 [ ] uzyskać `VERIFIED` final DB;
- 🟡 [ ] package + canonical attach → `ATTACHABLE`;
- 🟡 [ ] frozen private Recall baseline;
- 🟡 [ ] tylko potrzebne measured fixes;
- 🟡 [ ] manual L2/L3 review;
- 🟡 [ ] restart continuity;
- 🟡 [ ] final acceptance #59.

---

# 30. Zasada końcowa

> **Nie odbudowujemy pamięci po to, aby system miał więcej tekstu do przywołania. Odbudowujemy ją tak, aby każde użyte wspomnienie miało źródło, lineage, właściwy status epistemiczny i mogło przeżyć transport oraz restart bez zamiany pochodnej narracji w autobiograficzny fakt.**
