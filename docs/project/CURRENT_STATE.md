# Current project state

**Snapshot date:** 2026-09-07  
**Repository:** `SmuklyLew/jazn_latka`  
**Current master at documentation baseline:** `e828c2f4ab10a909d9d8b2324e69caf68f82c94d`  
**Current master version:** `16.3.25.5.38-ci-release-fixture-isolation`  
**Documentation convergence branch:** `update/v16.3.25.5.39-memory-affect-docs-convergence`

Ten plik jest krótkim overlayem stanu. Kanoniczną wersję zawsze czytać z `latka_jazn/version.py`, a status implementacji z kodu/testów/CI/PR/issue.

## Runtime / release foundations

- `run.py` pozostaje canonical lifecycle/operator surface.
- `AGENTS.md` jest routerem do właściwych runbooków.
- persistent-runtime, subject-root, host-finalization i host/executor truth foundations są częścią bieżącej linii.
- package/distribution/generator/dependency/plugin/CI hardening jest obecny do `.38`.
- `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` są synchronizowane wyłącznie kanonicznym release metadata flow, nie ręcznie.

## Memory Rebuild v4

**Status:** `MERGED / TOOL-PROTOCOL CONSOLIDATION COMPLETE`.

- PR #208 merged 2026-09-02;
- merge commit `601cf3fe977621c5552f7f6e32530da0128ccc8a`;
- issue #189 closed;
- Test00→Final engine/application foundation jest na master;
- ten status nie oznacza final private memory acceptance.

## Final private memory

Issue #59: `OPEN`.

Wymagane gates:

```text
SOURCE_INVENTORY_FROZEN
→ VERIFIED
→ ATTACHABLE
→ RETRIEVABLE
→ REVIEWED
→ ACCEPTED
```

Private Recall, false-memory/source discrimination, restart identity i review pozostają do wykonania na finalnym artefakcie.

## Emotion Engine / Affect

**Status:** `PLAN READY / CANONICAL IMPLEMENTATION NOT STARTED`.

Legacy affect/emotion/self/homeostasis modules istnieją i będą inventory input. Docelowy program wymaga:

```text
one AffectiveStateIntegrator
one AffectiveStateV2
EvidenceRef + AppraisalV2
FeelingRepresentation derived
accepted-turn persistence
bounded SelfState/Homeostasis/Salience effects
source-safe memory linkage
ablation
```

Affect inventory `A0` może być wykonany shadow-only po merge dokumentacji. Semantic canonical appraisal wymaga Polish NLP evidence. Active affective reranking wymaga frozen private Recall baseline.

## Attachment / multimodal

`OPEN`. Package/plugin capability infrastructure nie zastępuje canonical user attachment ingress. Nadal wymagane są exact provenance, secure bounded staging, extraction/type policy, capability routing i host→runtime E2E.

## Polish NLP

`OPEN / PARTIAL FOUNDATIONS`. Potrzebny jeden evidence-aware contract dla normalization, lexical provenance, ambiguity/OOV, negation/quotation/fiction i contextual/referential/temporal interpretation.

## Documentation

PR #231 został scalony. Obecna `.39` konwergencja domyka po-merge braki:

- usuwa compatibility pointers z aktywnego `docs/plans/`;
- zachowuje poprzedni stan w `only_to_check`;
- ustanawia jedną roadmapę v16.3.25.4→v17;
- przebudowuje Memory Restore + Affect jako sprzężony program;
- dodaje research/evidence register;
- naprawia stale `.36/378e9e6` metadata.

## v16.6

`FUTURE / EVIDENCE GATE`, nie monolityczny refactor. Wymaga jednocześnie runtime/host, attachment, NLP, accepted memory, canonical affect, source monitoring, ablation, model capability/context, package/cross-platform CI i governance evidence.

## v17

`FUTURE_CONDITIONAL`. Nie implementować przed v16.6 PASS. Kierunek: measured consolidation, nie dodawanie kolejnych antropomorficznych modułów.

## Governance

Ostatni odczyt GitHub dla mastera raportował `protected=false`. Finalny v16.6 wymaga ruleset/branch protection, jawnego równoważnego enforcement albo zaakceptowanego wyjątku z evidence.

## Documentation truth map

- `docs/plans/README.md` — planning index;
- `docs/plans/V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md` — program owner;
- `docs/plans/CURRENT_STEP.md` — current action;
- `docs/plans/PLAN_EXECUTION_HISTORY.md` — history/status;
- `docs/plans/LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md` — memory owner;
- `docs/plans/AFFECT_ENGINE_CONVERGENCE_PLAN.md` — affect owner;
- `docs/plans/RESEARCH_EVIDENCE_BASE.md` — research guidance;
- `docs/plans/V17_PLUS_SYSTEM_EVALUATION.md` — future entry gate;
- `docs/plans/only_to_check/` — `HISTORICAL_ONLY`.

`merged`, `working`, `verified`, `accepted` i `live` zawsze wynikają z właściwego evidence, nie z dokumentu, nazwy brancha, ZIP, SQLite lub stylu odpowiedzi.
