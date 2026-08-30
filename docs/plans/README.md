# Plans index — canonical execution map

**Updated:** 2026-08-30  
**Current release line at audit:** `16.3.25.3-release-metadata-semantics`  
**Current master HEAD:** intentionally not frozen; resolve and verify `master` / `origin/master` at execution time.

Ten katalog zawiera wyłącznie **bieżące kontrakty planistyczne, przyszłe release plans i audyty potrzebne do podejmowania decyzji**. Zakończone albo zastąpione implementation plans są w `docs/archive/plans/`.

---

# 1. Hierarchia pierwszeństwa

```text
AGENTS* + aktualny kod/testy/release reports
        |
        v
PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md
        |
        v
JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md
        |
        +-> release-specific active/next plan
        +-> cross-cutting hardening plan
        +-> evaluation/research reference

historical plans -> docs/archive/plans/
```

Jeżeli starszy dokument koliduje z aktualnym `AGENTS*`, kodem, raportem release lub canonical roadmap, starszy dokument jest historią.

---

# 2. Canonical project contract

| Dokument | Status | Znaczenie |
|---|---|---|
| `PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md` | **CANONICAL PLANNING CONTRACT** | definicje `Jaźń`, identity, continuity, memory, source monitoring, emotion, feeling/uczucie, awareness, Rest/Dream, confidence i capability evidence |
| `PLAN_COHERENCE_AUDIT_2026-08-30.md` | **AUDIT / REFERENCE** | audyt wszystkich planów, research check i branch audit |

Każdy nowy plan v16+ dziedziczy te definicje albo jawnie dokumentuje wyjątek.

---

# 3. Active / current execution

| Dokument | Status | Znaczenie |
|---|---|---|
| `JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md` | **ACTIVE / CANONICAL ROADMAP** | jedna nadrzędna kolejność release trainu do v16.6.0 |
| `JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md` | **ACTIVE / IN PROGRESS** | Memory Rebuild v4; #189; source-lineage/Test00→Final/no automatic activation |
| `JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md` | **PLANNED / NEXT TRAIN** | attachment/multimodal ingress; external content = data, nie authority |
| `JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md` | **PLANNED / CROSS-CUTTING** | autobiographical memory, causal continuity, affect/feeling semantics, confidence, ablation, Rest/Dream safety, governance |

---

# 4. System evaluation bridge — v16.6.0 → v17.0+

| Dokument | Status | Znaczenie |
|---|---|---|
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` | **REFERENCE / PREFERRED BROWSABLE FORM** | pełny audyt architektury Jaźni w Markdown |
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx` | **REFERENCE / ARCHIVAL SNAPSHOT** | oryginalny dokument audytu 2026-08-30; pozostaje niezmieniony |

Evaluation nie ustanawia release'u v17. Wymaganie blokujące v16.6 musi istnieć w roadmapie/cross-cutting planie.

---

# 5. Current release ordering

```text
16.3.25.3 current release line
-> 16.3.25.4 Memory Rebuild v4 consolidation
-> 16.3.26 attachment + multimodal ingress
-> 16.4.0-16.4.2 evidence-aware Polish NLP
-> 16.5.0 final Memory Rebuild / VERIFIED + source monitoring
-> 16.5.1 ATTACHABLE with lineage
-> 16.5.2+ autobiographical RETRIEVABLE
-> 16.5.y causal continuity / ACCEPTED candidate
-> 16.6.0 final convergence + cognitive/truth hardening / close #59
-> v17.0+ measured architecture consolidation
```

---

# 6. Cross-cutting assumptions

## Jaźń

Operational self-model + identity canon + runtime/memory lineage + truth boundaries + regulatory state. Nie sam prompt/persona i nie deklaracja phenomenal consciousness.

## Continuity

```text
runtime/root
> memory identity/provenance
> identity-canon
> finalization/turn lineage
> remembered corrections/procedures
> temporal/task continuity
> language/persona
```

## Memory

```text
RAW SOURCE
-> SEMANTIC INTERPRETATION
-> MEMORY PROJECTION
-> OPTIONAL REVIEW/PROMOTION
```

Derived/reflection/runtime/dream nie może udawać primary source.

## Emotion / feeling

- `emotion` = appraisal/regulatory computational state;
- `feeling/uczucie` = zintegrowana self-referential reprezentacja affective state dla regulacji/raportu;
- brak biologicznego/phenomenal claim;
- krytyczny affective module wymaga `effect_observed` albo pozostaje advisory.

## Capability truth

```text
present
-> constructible
-> callable
-> reachable_from_turn
-> effect_observed
-> persistence_verified
-> live_verified
```

File/module presence ≠ `working`.

---

# 7. Evaluation-derived gates assigned to v16

- **16.3.25.4:** source-aware RAW/L0; derived != primary.
- **16.3.26:** untrusted attachment data != instruction authority.
- **16.4.x:** NLP = query/lexical evidence, nie memory truth.
- **16.5.0:** source monitoring + genealogiczny primary/derived lineage.
- **16.5.2+:** source discrimination, false-memory, wrong-source, abstention, temporal/supersession, multi-session/referential continuity.
- **16.5.y:** causal-lineage-first continuity.
- **16.6.0:** confidence semantics, affect/cognitive influence registry, Rest/Dream false-memory safety, least privilege, architecture debt ledger i governance.

---

# 8. Historical plans

Indeks: `../archive/plans/README.md`

### v15

- `../archive/plans/v15/JAZN_V15_4_0_0_COGNITIVE_ARCHITECTURE.md`
- `../archive/plans/v15/JAZN_V15_4_2_0_REST_REPLAY_DREAM_CONTINUITY.md`
- `../archive/plans/v15/JAZN_V15_4_2_1_COGNITIVE_TRUTH_MEMORY_INTEGRATION_HARDENING.md`
- `../archive/plans/v15/JAZN_V15_5_LOCAL_FIRST_MEMORY_CLOUD.md`
- `../archive/plans/v15/MEMORY_CONTINUITY_VALIDATION_BACKLOG.md`
- `../archive/plans/v15/MEMORY_RECALL_HARDENING_PLAN.md` — phase 1 zmergowana w PR #125; żywe wymagania zostały wchłonięte przez v16.5–v16.6.

### v16 completed foundations

- `../archive/plans/v16/JAZN_V16_3_14_MEMORY_REBUILD_TEST00_RECALL.md`
- `../archive/plans/v16/JAZN_V16_3_22_ACTIVE_RUNTIME_SUBJECT_ROOT_IMPLEMENTATION_PLAN.md`
- `../archive/plans/v16/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_IMPLEMENTATION_PLAN.md`

### Runtime reference moved out of plans

- `../runtime/CHATGPT_HOST_FINALIZATION_PROTOCOL_TEST_MATRIX.md`

Historyczne plany zachowują treść, ale ich archiwalna ścieżka zapobiega pomyleniu z bieżącym poleceniem wykonawczym.

---

# 9. Branch status

`update/memory-rebuild-v4-roadmap-issues-sync` = **SUPERSEDED / FULLY MERGED**.

Przy audycie:

```text
branch HEAD = 03f5427106039970c08cce36336af4ce3eb11863
master      = 5e86793b1fff9ce6f7cbc6b435652681f6c207e5
branch ahead of master = 0
branch behind master    = 16
merge-base              = branch HEAD
```

Nie kontynuować na tym branchu i nie mergować go ponownie.

---

# 10. Issue map

- `#59` — **OPEN**: final private-memory acceptance; closure przy `ACCEPTED` / v16.6.
- `#189` — **OPEN / ACTIVE**: Memory Rebuild v4 consolidation.
- `#180` — **COMPLETED**: persistent active-memory recall E2E; pozostaje regression contract.
- `#185` — **COMPLETED**: host-finalization gate; pozostaje regression contract.

---

# 11. Rule for future planning

Nowy plan odpowiada co najmniej:

1. Jakiego stanu/evidence jest właścicielem?
2. Canonical state czy advisory signal?
3. Jak zachowuje source/provenance?
4. Jak wpływa na continuity?
5. Gdzie kończy się psychologiczna/neurobiologiczna analogia?
6. Jak definiuje `working` i jaki ma behavioral test?
7. Czy może tworzyć false-memory/self-amplifying derived data?
8. Jaki ma rollback/fail-closed path?

> **Im bardziej antropomorficznie brzmi nazwa funkcji, tym precyzyjniejszy musi być jej truth/evidence contract.**
