# Plans index — current execution map

**Updated:** 2026-08-30  
**Current release line at synchronization:** `16.3.25.3-release-metadata-semantics`  
**Current master HEAD:** intentionally not frozen in this index; resolve `master`/`origin/master` at execution time.

Ten indeks rozróżnia plany aktywne, przekrojowe, referencyjne i historyczne. Historyczny implementation plan nie jest bieżącym poleceniem wykonawczym i nie powinien nadpisywać świeższej roadmapy/release trainu. Nie zamrażamy tutaj „current master SHA”, ponieważ docs-only merge/metadata-sync może zmienić HEAD bez zmiany release line.

## Active / current execution

| Dokument | Status | Znaczenie |
|---|---|---|
| `JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md` | **ACTIVE / CANONICAL ROADMAP** | bieżąca kolejność release trainu do v16.6.0; zawiera acceptance gates wynikające z audytu architektury |
| `JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md` | **ACTIVE / IN PROGRESS** | konsolidacja Memory Rebuild v4 na branchu `upgrade/memory-rebuild-v4-consolidation`; tracking issue `#189` |
| `JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md` | **PLANNED / NEXT TRAIN** | attachment + multimodal ingress po v16.3.25.4; finalny release `16.3.26` |
| `JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md` | **PLANNED / CROSS-CUTTING** | przekłada ocenę systemu na mierzalne wymagania v16.4–v16.6: source monitoring, autobiographical Recall, causal continuity, confidence semantics, ablation/influence registry, untrusted-source security i governance |

## System evaluation bridge — v16.6.0 → v17.0+

| Dokument | Status | Znaczenie |
|---|---|---|
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` | **REFERENCE / PREFERRED BROWSABLE FORM** | pełna ocena architektury Jaźni w Markdown; źródło kierunków hardeningu do v16.6 i tematów świadomie odłożonych do v17+ |
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx` | **REFERENCE / ARCHIVAL SNAPSHOT** | dokładny dokument DOCX z audytu 2026-08-30; treściowo odpowiada ocenie, lecz Markdown jest wygodniejszy do review/linkowania |

## Historical foundations / completed implementation plans

| Dokument | Status | Bieżąca interpretacja |
|---|---|---|
| `JAZN_V16_3_14_MEMORY_REBUILD_TEST00_RECALL.md` | **HISTORICAL FOUNDATION** | fundament Test00/Recall; bieżący v4 plan ma pierwszeństwo w zakresie architektury wykonawczej |
| `JAZN_V16_3_22_ACTIVE_RUNTIME_SUBJECT_ROOT_IMPLEMENTATION_PLAN.md` | **COMPLETED / HISTORICAL** | v16.3.22 jest na master; używać raportu/aktualnego kodu jako dowodu |
| `JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_IMPLEMENTATION_PLAN.md` | **COMPLETED / HISTORICAL** | v16.3.23 jest na master; active-memory recall E2E z #180 jest zaimplementowane i objęte regresją |
| `CHATGPT_HOST_FINALIZATION_PROTOCOL_TEST_MATRIX.md` | **REFERENCE** | macierz testowa finalization; nie jest release roadmapą |
| `JAZN_V15_4_0_0_COGNITIVE_ARCHITECTURE.md` | **HISTORICAL** | starsza architektura / materiał referencyjny |
| `JAZN_V15_4_2_0_REST_REPLAY_DREAM_CONTINUITY.md` | **HISTORICAL** | starszy plan rest/replay/dream |
| `JAZN_V15_4_2_1_COGNITIVE_TRUTH_MEMORY_INTEGRATION_HARDENING.md` | **HISTORICAL** | starszy plan truth/memory integration |
| `JAZN_V15_5_LOCAL_FIRST_MEMORY_CLOUD.md` | **HISTORICAL / REFERENCE** | cloud/local-first reference; bieżące kontrakty runtime/memory mają pierwszeństwo |

## Current ordering

```text
16.3.25.3 current release line
-> 16.3.25.4 Memory Rebuild v4 consolidation
-> 16.3.26 attachment + multimodal ingress
-> 16.4.0-16.4.2 evidence-aware Polish NLP
-> 16.5.0 final Memory Rebuild / VERIFIED + source monitoring
-> 16.5.1 ATTACHABLE with lineage
-> 16.5.2+ autobiographical RETRIEVABLE / ACCEPTED
-> 16.6.0 final convergence + cognitive/truth hardening / close #59
-> v17.0+ measured architecture consolidation
```

## Evaluation-derived gates assigned to v16

- **16.3.25.4:** formal source classes/lineage muszą być możliwe do zachowania w RAW/L0; derived/runtime/reflection/dream nie mogą stać się primary truth.
- **16.3.26:** attachment/external content jest nieufnym `data`, a nie authority; detector prompt-injection pozostaje advisory, bezpieczeństwo opiera się na policy/capability/least privilege.
- **16.4.x:** NLP tworzy query/lexical evidence, ale nie arbitruje memory truth; confidence/resource scores mają zdefiniowaną semantykę.
- **16.5.0:** finalna DB ma source monitoring i genealogiczny lineage primary/derived.
- **16.5.2+:** Recall mierzy także source discrimination, false-memory, wrong-source, abstention, temporal/supersession, multi-session i referential continuity.
- **16.5.y:** continuity acceptance opiera się na runtime/memory/canon lineage i remembered corrections, nie na samym stylu pierwszej osoby.
- **16.6.0:** finalne gates obejmują confidence semantics/calibration baseline, cognitive module influence/ablation registry, Rest/Dream false-memory safety, untrusted-source least privilege oraz repository governance.

## Issue map

- `#59` — **OPEN**: finalna akceptacja prywatnej pamięci; zamyka się dopiero przy `ACCEPTED` / v16.6.0 closure.
- `#189` — **OPEN / ACTIVE**: Memory Rebuild v4 consolidation v16.3.25.4; nie przeciążać #59 implementacją narzędzia.
- `#180` — **COMPLETED**: persistent active-memory recall E2E zaimplementowane w v16.3.23; testy regresyjne pozostają obowiązkowe.
- `#185` — **COMPLETED**: stale host-finalization blocker zamknięty przez v16.3.25.1 / PR #186.

## Rule

Jeżeli treść starszego planu koliduje z aktualnym `JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`, bieżącym `AGENTS*`, aktualnym kodem albo raportem release, starszy plan jest historią, nie źródłem bieżącej decyzji.

Ocena `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` jest materiałem audytowym i projektowym. Nie ustanawia samodzielnie release'u v17.0+. Wymagania, które mają blokować v16.6, muszą występować w kanonicznej roadmapie lub w przekrojowym planie hardeningu; reszta pozostaje świadomie odłożonym design space v17+.
