# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Stan:** 2026-09-07  
**Baza:** `master @ e828c2f4ab10a909d9d8b2324e69caf68f82c94d` / `16.3.25.5.38-ci-release-fixture-isolation`  
**Branch:** `update/v16.3.25.5.39-memory-affect-docs-convergence`

## 1. Stan programu

```text
Memory Rebuild v4 tool/protocol      MERGED / PR #208 / #189 closed
16.3.25.5.x hardening                MERGED do .38
PR #231 docs convergence             MERGED
planning rewrite Memory + Affect     IN_PROGRESS on this branch
final private memory #59             OPEN / NOT ACCEPTED
attachment + multimodal ingress      OPEN
Polish NLP evidence                  OPEN
canonical Affect Engine              PLAN READY / NOT IMPLEMENTED
v16.6 evidence gate                  FUTURE
v17 consolidation                    FUTURE_CONDITIONAL
```

## 2. Bieżący krok — planning truth closure

Ta zmiana:

- zachowuje stan po PR #231 w `only_to_check`;
- usuwa stare compatibility pointery z aktywnego `docs/plans/`;
- ustanawia jedną roadmapę v16.3.25.4→v17;
- przepisuje Memory Restore i Affect Plan jako sprzężone, ale osobne authority;
- dodaje research/evidence base;
- synchronizuje current-state metadata;
- podnosi wersję zgodnie z repo policy;
- nie zmienia runtime behavior.

Exit: w `docs/plans/` pozostaje tylko aktywna warstwa kanoniczna, a historyczne plany są wyłącznie w `only_to_check/` lub `docs/archive/`.

## 3. Co wolno rozpocząć po merge dokumentacji

### A0 — Affect inventory / shadow baseline

Dozwolone bez visible behavior change:

```text
call/import graph
writers/readers
legacy affect authorities
persistence/finalization points
behavioral fixtures
latency baseline
role/debt classification
shadow observability
```

Jeszcze nie: canonical appraisal cutover, memory reranking, resonance ani usuwanie legacy modules bez ablation.

### P0 — attachment ingress inventory

Fresh-master audit host/capability/attachment surfaces może przygotować implementation branch.

## 4. Kolejność produktu

1. **P0 attachment/multimodal ingress** — provenance, safe staging, capability routing, no auto-memory, E2E.
2. **P1 evidence-aware Polish NLP** — normalization, lexical/resource provenance, ambiguity/OOV, negation/quotation/fiction i contextual evidence.
3. **M0–M2 final private restore** — source freeze → Test00–04 → final DB → package → attach; gates `VERIFIED`, `ATTACHABLE`.
4. **M3 frozen Recall baseline** — bez affective rerank; candidate `RETRIEVABLE`.
5. **A1–A4 canonical affect** — appraisal SHADOW → dynamics/persistence → canonical cutover → affect snapshot linkage.
6. **M4 measured retrieval fixes** tylko jeśli baseline tego wymaga.
7. **A5–A7 memory↔affect** — rerank SHADOW → A/B → one-pass resonance.
8. **M5 review + restart** — manual L2/L3 + memory identity continuity; `ACCEPTED_CANDIDATE`.
9. **v16.6 gate** — pełny evidence package.
10. **v17** — dopiero po v16.6 PASS.

## 5. Zależności twarde

```text
canonical semantic affect requires Polish NLP evidence
active affective rerank requires frozen Memory Recall baseline
resonance requires MemoryUseGate PASS
memory ACCEPTED requires source/restart/false-memory evidence
v17 requires accepted memory + canonical affect evidence
```

## 6. Przed każdym implementation branch

Fresh master, obowiązujące `AGENTS*`, restore point, inventory rzeczywistego kodu, hypothesis + acceptance tests, legalny version bump, najmniejszy kompletny zakres, A/B/ablation dla retrieval/kognicji i zero osłabienia truth/source/privacy gates.

> Aktualnie domykamy jedną kanoniczną dokumentację Memory↔Affect. Po jej merge legalne są Affect A0 i przygotowanie attachment/NLP; aktywna integracja affect z recall dopiero po finalnej pamięci i zamrożonym baseline.
