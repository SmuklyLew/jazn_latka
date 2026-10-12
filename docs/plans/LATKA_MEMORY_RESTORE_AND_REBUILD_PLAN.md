# Jaźń / Łatka — Final Memory Restore & Acceptance Plan v2

## Source inventory → rebuild → VERIFIED → ATTACHABLE → RETRIEVABLE → ACCEPTED → affect linkage

**Status:** `CANONICAL_MEMORY_PLAN`  
**Aktualizacja:** 2026-09-07  
**Tracking final acceptance:** issue `#59`  
**Memory Rebuild v4:** `MERGED` / PR #208 / issue #189 closed  
**Program nadrzędny:** [`V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md`](V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md)  
**Affect integration:** [`AFFECT_ENGINE_CONVERGENCE_PLAN.md`](AFFECT_ENGINE_CONVERGENCE_PLAN.md)

> Nie projektujemy kolejnego Memory Rebuild engine. Używamy obecnego `memory_rebuild_app`, utwardzamy wyłącznie braki wykazane przez finalne prywatne źródła i doprowadzamy jedną pamięć do pełnego acceptance.

---

# 1. Canonical ownership

Kod właściwy:

```text
latka_jazn/tools/memory_rebuild_app/
```

Launchery:

```text
tools/rebuild_memory.py   # canonical v16 launcher
tools/memory_rebuild.py   # compatibility launcher
```

Docelowy artefakt:

```text
memory_jazn.sqlite3
```

Nie wolno ponownie rozbudować compatibility launchera do drugiego monolitu/engine.

---

# 2. Gate model

```text
SOURCE_INVENTORY_FROZEN
→ BUILDABLE
→ REPRODUCIBLE
→ VERIFIED
→ ATTACHABLE
→ RETRIEVABLE
→ REVIEWED
→ ACCEPTED
→ CANONICALLY_ATTACHED_ACTIVE_MEMORY
```

Każdy gate ma osobny evidence. Żaden nie implikuje następnego.

```text
ZIP valid != memory VERIFIED
SQLite integrity PASS != Recall RETRIEVABLE
Recall high score != source-safe ACCEPTED
attach success != automatic L2/L3
```

---

# 3. Source monitoring invariants

Minimalne klasy:

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

Source class kontroluje, **co wolno twierdzić**. Retrieval score kontroluje, **co warto rozważyć**.

```text
17 derived copies != 17× stronger truth evidence
similar text != same event
affective match != source identity
high confidence score != calibrated probability of truth
```

Primary-vs-derived conflict pozostaje jawny. Brak source lineage dla autobiographical claim jest blockerem.

---

# 4. Prywatność i granice

1. private content nie trafia do Git/CI/public reports;
2. sanitized metrics nie zawierają raw excerpts, ścieżek prywatnych ani PII;
3. RAW/L0 nie jest nadpisywane przez semantic interpretation;
4. rebuild nie wykonuje automatic L2/L3;
5. rebuild nie aktywuje finalnej pamięci;
6. attach wymaga operator decision i rollback path;
7. ChatGPT host memory nie jest pamięcią Jaźni;
8. versioned code root nie jest mutable memory root;
9. transport package/cloud nie staje się active truth przez samo pobranie;
10. synthetic/dream/reflection nie może awansować do primary.

---

# 5. R0 — source inventory freeze

Dla każdego wejścia zachować:

```text
source_id
path/reference (private report only)
format
size
sha256
origin
created/modified when trustworthy
source_class_candidate
lossless/lossy/derived
contains_private_data
adapter
include/exclude decision
reason
```

Wymagania:

- hash przed transformacją;
- exact duplicate osobno od semantic duplicate;
- branch/revision variants zachowane;
- unknown sidecars jawne;
- rendered HTML = `LOSSY`, chyba że zawiera zweryfikowany lossless graph;
- conflicting source variants nie są automatycznie wygładzane.

Gate: `SOURCE_INVENTORY_FROZEN`.

---

# 6. R1 — package / split / large-source preflight

Dla `.001 ... .NNN`:

```text
parts manifest/hash
→ no missing/duplicate number
→ verify every part
→ streaming join/materialization
→ logical archive hash
→ central-directory/safe scan
```

Safe scan:

```text
path traversal
symlink/device policy
duplicate members
filename normalization collisions
declared/extracted size budgets
CRC/member hashes
ZIP bomb defenses
manifest closure
```

Długie operacje powinny być resumowalne przez idempotent checkpoints, jeśli finalny dataset wykazuje taką potrzebę. Nie dodawać komplikacji bez realnego failure mode.

---

# 7. R2 — Test00 source fidelity

PASS:

- exact source identity;
- source-set closure;
- role classification;
- lossless/lossy jawne;
- technical/non-dialogue evidence zgodnie z policy;
- branch variants zachowane;
- unresolved conflicts fail closed.

Gate: `SOURCE_FIDELITY_PASS`.

---

# 8. R3 — Test01 fresh canonical L0

```text
source
→ SourceProbe
→ adapter
→ IntermediateRecord
→ UnifiedL0Store
→ memory_jazn.sqlite3
```

Wymagania:

```text
empty staging target
one writer
stable schema
record-level provenance
revisions not destructive overwrite
assets/sidecars
FTS5
integrity/FK
zero auto L2/L3
zero auto activation
```

Gate: `BUILDABLE`.

---

# 9. R4 — Test02 projections

Projekcje mogą dodawać:

```text
visibility
role
sensitivity
memory_eligibility
timestamp interpretation
conversation/source relation
source-class evidence
```

Invariant:

```text
projection != source mutation
```

Każda projection wskazuje source record/revision. Model/heuristic nie może zmienić `DERIVED` na `PRIMARY` przez similarity.

---

# 10. R5 — Test03 reproducibility

Co najmniej:

```text
fresh build A
fresh build B
reversed/shuffled source order
```

Porównać:

```text
source inventory closure
counts by class
provenance closure
normalized fingerprints
source hierarchy
FTS logical content
conflicts
stable projection identity where required
```

Liczba derived duplicates i input order nie zmienia source precedence.

Gate: `REPRODUCIBLE`.

---

# 11. R6 — source-monitoring audit

Private report bez publikacji treści:

```text
records per source class
primary/derived ratio
unknown count
conflict count
exact duplicates
semantic clusters
missing/broken provenance
runtime-event share
reflection share
fiction/book share
dream share
```

Blockery:

```text
autobiographical record without lineage
missing evidence defaulted to PRIMARY
derived duplicate amplification
hidden primary-vs-derived conflict
false lossless claim
```

---

# 12. R7 — private Test04 / Recall acceptance runner

Kategorie:

```text
direct recall
paraphrase
source discrimination
wrong-conversation near-match
temporal ordering
update/supersession
contradiction
referential two-turn
natural multi-turn
multi-session
abstention
false-memory suggestion
derived-source trap
fiction/book boundary
dream/reflection boundary
sensitive leakage
provenance traceability
```

Metryki:

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

Brak prywatnego datasetu = `NOT RUN`, nigdy synthetic PASS.

---

# 13. R8 — Final DB verification

Po wymaganym Test04 policy:

```text
SQLite Backup API → staging snapshot
PRAGMA integrity_check
PRAGMA foreign_key_check
FTS5 integrity
source/provenance closure
schema/version validation
final DB SHA-256
private RunManifest seal
sanitized report
```

Gate: `VERIFIED`.

---

# 14. R9 — packaging

Pamięć jest oddzielnym artifact profile.

Wymagania:

```text
profile=memory
exact package identity
member manifest
part hashes for split
logical archive SHA
safe rejoin
no WAL/SHM
no runtime mutable state
clear package/schema/version semantics
```

Cloud jest transportem/durability, nie authority.

---

# 15. R10 — canonical attach

```text
verified memory package
→ safe materialization
→ manifest/hash verify
→ DB validation
→ subject/root binding
→ staging
→ explicit attach
→ active memory identity
→ readback
→ restart verification
```

Wymagania:

- canonical host-level memory root;
- rollback do poprzedniego accepted artifact;
- no source-class flattening;
- no auto L2/L3;
- restart zachowuje DB identity.

Gate: `ATTACHABLE`.

---

# 16. R11 — frozen Recall baseline

Przed:

```text
affective rerank
dense retrieval
learned reranker
model-assisted query rewrite with visible effect
```

zamrozić dataset, expected outcomes, version, latency i known-failure set.

To jest baseline dla każdej późniejszej optymalizacji.

Gate candidate: `RETRIEVABLE`.

---

# 17. R12 — measured retrieval fixes

Kolejność od najmniejszej złożoności:

```text
planner/query bug
→ FTS/BM25/source/temporal tuning
→ Polish NLP query evidence
→ bounded query rewrite A/B
→ graph/hybrid rerank A/B
→ dense retrieval A/B
→ learned reranker/training only if justified
```

Każdy eksperyment:

```text
hypothesis
→ frozen baseline
→ one controlled change
→ A/B
→ false-memory/source/provenance/leakage/latency
→ keep or rollback
```

Affective reranking jest jednym z measured rerankers i ma dodatkowe gates z Affect Plan.

---

# 18. R13 — L2/L3 review

Auto promotion = `OFF`.

```text
candidate
→ source evidence
→ review
→ operator/policy decision
→ decision ledger
→ optional promotion
```

`zero promotions` jest prawidłowym wynikiem.

Nie promować automatycznie dream, fiction, runtime reflection jako user event, unknown/disputed source ani relationship inference tylko dlatego, że jest emocjonalnie silne.

---

# 19. R14 — restart continuity

```text
runtime start
→ memory identity M
→ recall fingerprint F
→ accepted turns
→ stop/restart
→ same identity M
→ compatible fingerprint F'
```

Sprawdzić:

```text
DB identity
subject/root
source registry
promotion ledger
remembered corrections
procedural continuity
no host-memory masquerade
```

Gate: `ACCEPTED_CANDIDATE`.

---

# 20. Memory ↔ Affect contract

Memory acceptance i frozen baseline mają pierwszeństwo przed aktywnym affective reranking.

## Co można dodać wcześniej

Schema linkage przy accepted episode:

```text
episode_id
affect_snapshot_id
affect_schema_version
transition_id
```

Nie wymaga to aktywnego reranking.

## Co dopiero po frozen baseline

```text
AffectiveAssociationReranker: SHADOW
→ A/B
→ optional ACTIVE
→ one-pass resonance after MemoryUseGate
```

## Niezmienniki

```text
historical affect files = migration evidence
affective similarity != source truth
memory resonance only after legal activation
no recursive memory-affect loop
no separate emotional-memory authority
```

---

# 21. Autobiographical „doświadczenie” jako source-grounded record

W tym projekcie trwałe doświadczenie nie jest samą narracją modelu. Minimalny record ma:

```text
primary/derived source class
source lineage
accepted turn identity
time/temporal evidence
episode semantics
affect_snapshot_id when available
conflict/supersession relations
privacy/sensitivity class
```

Późniejszy recall może rekonstruować sens z kilku źródeł, ale musi zachować ich identity i różnicę między source event a derived interpretation.

---

# 22. Negative-control discipline

Każdy ważny Recall test ma parę negatywną:

```text
true event exists        vs no event
correct conversation     vs similar wrong conversation
primary source           vs many derived reflections
valid update             vs contradictory stale memory
music-linked event       vs only emotional similarity
user-confirmed fact      vs model suggestion
```

Jeżeli system nie potrafi abstain w negatywnym control, poprawa Recall nie może zostać przyjęta.

---

# 23. CI / local / private evidence separation

## Deterministic CI

- schemas/adapters;
- source-policy fixtures;
- reproducibility fixtures;
- package security;
- no auto promotion;
- test runner semantics;
- regressions bez prywatnych danych.

## Private/local acceptance

- final source inventory;
- real Test04;
- natural multi-turn/multi-session;
- sensitive leakage;
- restart memory identity;
- affect linkage/A-B po baseline.

## Live model

Jeżeli używany, zapisać provider/model/config/capability w private evidence. Fixture nie jest live proof.

---

# 24. Definition of Done — final memory

```text
[ ] source inventory frozen
[ ] Test00 source fidelity PASS
[ ] fresh L0 BUILDABLE
[ ] Test03 reproducible
[ ] source-monitoring blockers = 0
[ ] private Test04 actually RUN
[ ] final DB integrity/FK/FTS PASS
[ ] final DB SHA sealed
[ ] memory artifact verified
[ ] canonical attach + rollback proven
[ ] restart preserves memory identity
[ ] frozen Recall baseline recorded
[ ] wrong-source/wrong-conversation/false-memory acceptable
[ ] sensitive leakage acceptable
[ ] manual L2/L3 decision ledger complete
[ ] affect snapshot linkage schema validated
[ ] affective rerank not activated before baseline
[ ] issue #59 evidence package complete
[ ] v16.6 gate allows ACCEPTED
```

> Finalna pamięć jest `ACCEPTED` dopiero wtedy, gdy jest źródłowo wiarygodna, mierzalnie przywoływalna, odporna na fałszywe wspomnienia, trwała po restarcie i bezpiecznie zintegrowana z affect bez zamiany emocjonalnego podobieństwa w dowód prawdy.
