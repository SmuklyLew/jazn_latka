# Dokumentacja Jaźni — mapa i źródła prawdy

**Aktualizacja:** 2026-09-07  
**Zweryfikowany master:** `e828c2f4ab10a909d9d8b2324e69caf68f82c94d` / `16.3.25.5.38-ci-release-fixture-isolation`  
**Bieżąca dokumentacyjna linia zmian:** `update/v16.3.25.5.39-memory-affect-docs-convergence`

Dokumentacja jest uporządkowana według odpowiedzialności, aktualności i poziomu dowodu.

## Zacznij tutaj

1. [`../AGENTS.md`](../AGENTS.md) — router instrukcji.
2. [`project/CURRENT_STATE.md`](project/CURRENT_STATE.md) — krótki overlay rzeczywistego stanu projektu.
3. [`plans/README.md`](plans/README.md) — kanoniczna mapa aktywnych planów.
4. [`plans/V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md`](plans/V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md) — nadrzędna roadmapa v16.3.25.4→v17.
5. [`plans/CURRENT_STEP.md`](plans/CURRENT_STEP.md) — bieżący legalny krok.

## Aktywna warstwa planistyczna

```text
plans/
├── README.md
├── V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md
├── CURRENT_STEP.md
├── PLAN_EXECUTION_HISTORY.md
├── LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md
├── AFFECT_ENGINE_CONVERGENCE_PLAN.md
├── RESEARCH_EVIDENCE_BASE.md
├── V17_PLUS_SYSTEM_EVALUATION.md
└── only_to_check/          # wyłącznie historia / NON_AUTHORITATIVE
```

Historyczne plany nie pozostają jako compatibility pointery w aktywnym root `plans/`.

## Główne domeny dokumentacji

- `project/` — current state, release timeline, assumptions, architecture/governance.
- `plans/` — tylko bieżące owner plans + historyczne `only_to_check/`.
- `memory/` — operacyjna dokumentacja pamięci i narzędzi.
- `runtime/` — lifecycle/host/runtime/operator.
- `packaging/` — pakowanie, release i dystrybucja.
- `nlp/` — kontrakty NLP/resources.
- `tools/` — dokumentacja narzędzi.
- `reports/` — aktualne raporty, jeśli nie należą do archiwum.
- `archive/` — historyczne release reports, patches, plans, reviews i artefakty dokumentacyjne.

## Hierarchia prawdy

```text
system/developer/user instructions
→ AGENTS* in scope
→ current code/tests/machine evidence
→ current master/PR/issue/CI
→ project/CURRENT_STATE.md
→ plans canonical roadmap/current step/history
→ domain plan
→ research guidance
→ only_to_check/
→ archive/
```

Stary dokument nie staje się aktualny przez podobną nazwę wersji. `ACTIVE`, `IN_PROGRESS`, branch i SHA zapisane w `only_to_check/` lub `archive/` są historycznym snapshotem.

## Centralny program: Memory + Affect

Bieżąca roadmapa traktuje Final Memory Restore i Emotion Engine jako silnie sprzężone, ale z oddzielnymi authority:

```text
Memory owns source/provenance/retrieval
Affect owns appraisal/state/dynamics/regulation
MemoryUseGate owns legal memory use boundary
accepted-turn finalization owns durable affect commit boundary
```

Affect może bounded wpływać na memory probe/ranking dopiero po source eligibility i frozen baseline. Nigdy nie zwiększa source truth.

## Granica naukowa

Terminy `emotion`, `feeling`, `homeostasis`, `dream`, `neurocognitive` itd. oznaczają funkcjonalne kontrakty software. Źródła psychologiczne, affective-computing i LLM benchmarks są podstawą hipotez/testów, nie dowodem biologicznych procesów ani phenomenal consciousness.
