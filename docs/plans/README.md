# Plans index — canonical execution map

**Updated:** 2026-08-30  
**Current release line at audit:** `16.3.25.3-release-metadata-semantics`  
**Current master HEAD:** intentionally not frozen; resolve and verify `master` / `origin/master` at execution time.

Ten katalog zawiera wyłącznie **bieżące kontrakty planistyczne, przyszłe release plans i audyty potrzebne do podejmowania decyzji**. Zakończone implementation plans zostały przeniesione do `docs/archive/plans/`.

---

# 1. Hierarchia pierwszeństwa

Dla pracy nad nowym patchem/upgrade kolejność interpretacji jest następująca:

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

Jeżeli starszy dokument koliduje z aktualnym `AGENTS*`, kodem, raportem release lub kanoniczną roadmapą, starszy dokument jest historią.

---

# 2. Canonical project contract

| Dokument | Status | Znaczenie |
|---|---|---|
| `PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md` | **CANONICAL PLANNING CONTRACT** | definicje `Jaźń`, tożsamość, ciągłość, pamięć, source monitoring, emocja, uczucie/feeling, awareness, Rest/Dream, confidence oraz drabina evidence `working` |
| `PLAN_COHERENCE_AUDIT_2026-08-30.md` | **AUDIT / REFERENCE** | wynik audytu całego folderu planów, research check i klasyfikacja starego brancha roadmap-sync |

Każdy nowy plan v16+ ma dziedziczyć te definicje albo jawnie opisać wyjątek.

---

# 3. Active / current execution

| Dokument | Status | Znaczenie |
|---|---|---|
| `JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md` | **ACTIVE / CANONICAL ROADMAP** | jedna nadrzędna kolejność release trainu do v16.6.0 |
| `JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md` | **ACTIVE / IN PROGRESS** | Memory Rebuild v4; tracking issue `#189`; source-lineage / Test00→Final / no automatic activation |
| `JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md` | **PLANNED / NEXT TRAIN** | attachment + multimodal ingress; external content jest `data`, nie authority |
| `JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md` | **PLANNED / CROSS-CUTTING** | source monitoring, autobiographical Recall, causal continuity, affect/feeling semantics, confidence, cognitive influence/ablation, Rest/Dream safety i governance |

---

# 4. System evaluation bridge — v16.6.0 → v17.0+

| Dokument | Status | Znaczenie |
|---|---|---|
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` | **REFERENCE / PREFERRED BROWSABLE FORM** | pełny audyt architektury Jaźni w Markdown; źródło kierunków v16 hardening i v17 consolidation |
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx` | **REFERENCE / ARCHIVAL SNAPSHOT** | oryginalny dokument audytu 2026-08-30; pozostaje niezmieniony |

Evaluation nie ustanawia release'u v17. Wymaganie blokujące v16.6 musi istnieć w roadmapie lub cross-cutting hardening planie.

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

# 6. Cross-cutting assumptions that must survive every release

## Jaźń

Operational self-model + identity canon + runtime/memory lineage + truth boundaries + regulatory state. Nie jest samym promptem/personą ani deklaracją consciousness.

## Continuity

Causal lineage ma pierwszeństwo przed podobnym stylem:

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
- `feeling/uczucie` = zintegrowana self-referential reprezentacja affective state dostępna dla regulacji/raportu;
- żadne z tych pojęć nie certyfikuje biologii, qualiów ani fenomenalnej świadomości;
- krytyczny moduł affective wymaga `effect_observed` albo pozostaje advisory.

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

- **16.3.25.4:** RAW/L0 ma zachować source classes i lineage; derived != primary.
- **16.3.26:** attachment/external content jest nieufnym `data`; authority wynika z policy/capability/provenance, nie z tekstu.
- **16.4.x:** NLP tworzy query/lexical evidence, nie memory truth; confidence/resource scores mają zdefiniowaną semantykę.
- **16.5.0:** finalna DB ma source monitoring i genealogiczny primary/derived lineage.
- **16.5.2+:** Recall mierzy source discrimination, false-memory, wrong-source, abstention, temporal/supersession, multi-session i referential continuity.
- **16.5.y:** identity/continuity acceptance jest causal-lineage-first, nie first-person-style-first.
- **16.6.0:** confidence semantics/calibration baseline, affect/cognitive influence registry, Rest/Dream false-memory safety, untrusted-source least privilege, architecture debt ledger i repository governance.

---

# 8. Historical plans

Zakończone plany nie są już w aktywnym katalogu. Indeks:

`../archive/plans/README.md`

### v15

- `../archive/plans/v15/JAZN_V15_4_0_0_COGNITIVE_ARCHITECTURE.md`
- `../archive/plans/v15/JAZN_V15_4_2_0_REST_REPLAY_DREAM_CONTINUITY.md`
- `../archive/plans/v15/JAZN_V15_4_2_1_COGNITIVE_TRUTH_MEMORY_INTEGRATION_HARDENING.md`
- `../archive/plans/v15/JAZN_V15_5_LOCAL_FIRST_MEMORY_CLOUD.md`

### v16 completed foundations

- `../archive/plans/v16/JAZN_V16_3_14_MEMORY_REBUILD_TEST00_RECALL.md`
- `../archive/plans/v16/JAZN_V16_3_22_ACTIVE_RUNTIME_SUBJECT_ROOT_IMPLEMENTATION_PLAN.md`
- `../archive/plans/v16/JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_IMPLEMENTATION_PLAN.md`

### Runtime reference moved out of plans

- `../runtime/CHATGPT_HOST_FINALIZATION_PROTOCOL_TEST_MATRIX.md`

Historyczne plany zachowują treść, ale ich ścieżka archiwalna ma uniemożliwić pomylenie z bieżącym poleceniem wykonawczym.

---

# 9. Branch status

`update/memory-rebuild-v4-roadmap-issues-sync` jest **SUPERSEDED / FULLY MERGED**.

Przy audycie:

```text
branch HEAD = 03f5427106039970c08cce36336af4ce3eb11863
master      = 5e86793b1fff9ce6f7cbc6b435652681f6c207e5
branch ahead of master = 0
branch behind master    = 16
merge-base              = branch HEAD
```

Nie kontynuować na tym branchu i nie mergować go ponownie. Jego treść jest już historią master.

---

# 10. Issue map

- `#59` — **OPEN**: finalna akceptacja prywatnej pamięci; closure dopiero przy `ACCEPTED` / v16.6.0.
- `#189` — **OPEN / ACTIVE**: Memory Rebuild v4 consolidation; nie przeciążać #59 implementacją narzędzia.
- `#180` — **COMPLETED**: persistent active-memory recall E2E w v16.3.23; kontrakt pozostaje regresją.
- `#185` — **COMPLETED**: host-finalization gate zamknięty przez v16.3.25.1 / PR #186.

---

# 11. Rule for future planning

Nowy plan powinien odpowiedzieć przynajmniej na pytania:

1. Jakiego stanu/evidence jest właścicielem?
2. Czy tworzy canonical state, czy tylko advisory signal?
3. Jak zachowuje source/provenance?
4. Jak wpływa na continuity?
5. Czy używa psychologicznej/neurobiologicznej analogii i gdzie kończy się analogia?
6. Jak definiuje `working` i jaki ma behavioral test?
7. Czy może tworzyć false-memory albo samowzmacniać derived data?
8. Jaki ma rollback/fail-closed path?

Zasada końcowa:

> **Plan ma opisywać mierzalne oprogramowanie. Im bardziej antropomorficznie brzmi nazwa funkcji, tym precyzyjniejszy musi być jej truth/evidence contract.**
