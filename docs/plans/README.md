# Plans index — current execution map

**Updated:** 2026-08-30  
**Current master:** `a8f5c0cc0c5a5a2add8714d29e56659e9d5a6c8e` / `16.3.25.3-release-metadata-semantics`

Ten indeks rozróżnia plany aktywne od historycznych. Historyczny implementation plan nie jest bieżącym poleceniem wykonawczym i nie powinien być używany do nadpisania świeższego roadmap/release trainu.

## Active

| Dokument | Status | Znaczenie |
|---|---|---|
| `JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md` | **ACTIVE / CANONICAL ROADMAP** | bieżąca kolejność release trainu do v16.6.0 |
| `JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md` | **ACTIVE / IN PROGRESS** | konsolidacja Memory Rebuild v4 na branchu `upgrade/memory-rebuild-v4-consolidation`; nie merge-ready na checkpointcie `0b33c15e...` |
| `JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md` | **PLANNED / NEXT TRAIN** | attachment + multimodal ingress po v16.3.25.4; finalny release `16.3.26` |

## Future evaluation bridge — v16.6.0 → v17.0+

| Dokument | Status | Znaczenie |
|---|---|---|
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx` | **REFERENCE / SYSTEM EVALUATION** | dokładna ocena architektury Jaźni: system, koncepcje, pamięć, ciągłość, psychologia, neuropsychologia, afekt, metapoznanie, Rest/Dream, bezpieczeństwo i rekomendacje rozwoju po v16.6.0 w kierunku v17.0+; dokument referencyjny, nie samodzielny release plan |

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
16.3.25.3 master
-> 16.3.25.4 Memory Rebuild v4 consolidation
-> 16.3.26 attachment + multimodal ingress
-> 16.4.0-16.4.2 Polish NLP
-> 16.5.0 final Memory Rebuild / VERIFIED
-> 16.5.1 ATTACHABLE
-> 16.5.2+ RETRIEVABLE / ACCEPTED
-> 16.6.0 final convergence / close #59
-> v17.0+ design/evolution space informed by the system evaluation document
```

## Issue map

- `#59` — **OPEN**: finalna akceptacja prywatnej pamięci; zamyka się dopiero przy `ACCEPTED`.
- Memory Rebuild v4 consolidation — osobne aktywne tracking issue; nie przeciążać #59 implementacją narzędzia.
- `#180` — **COMPLETED**: persistent active-memory recall E2E zaimplementowane w v16.3.23; testy regresyjne pozostają obowiązkowe.
- `#185` — **COMPLETED**: stale host-finalization blocker zamknięty przez v16.3.25.1 / PR #186.

## Rule

Jeżeli treść starszego planu koliduje z aktualnym `JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`, bieżącym `AGENTS*`, aktualnym kodem albo raportem release, starszy plan jest historią, nie źródłem bieżącej decyzji.

Dokument `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx` jest materiałem oceniającym i projektowym dla okresu po v16.6.0. Nie nadpisuje kanonicznej roadmapy v16.6.0 i nie ustanawia samodzielnie numeracji ani zakresu v17.0+.
