# Dokumentacja Jaźni — mapa i źródła prawdy

**Aktualizacja mapy:** 2026-09-07  
**Zweryfikowany master przy reorganizacji:** `378e9e6aceb83edbd679751e19cbe5c64c978025` / `16.3.25.5.36-ci-archive-scope-contract-hardening`

Dokumentacja jest porządkowana według **właściciela, aktualności i poziomu dowodu**.

## Zacznij tutaj

1. [`../AGENTS.md`](../AGENTS.md) — router odpowiedzialności hostów/agentów;
2. [`project/CURRENT_STATE.md`](project/CURRENT_STATE.md) — bieżący overlay mastera i otwartych gates;
3. [`plans/README.md`](plans/README.md) — kanoniczna mapa aktualnych planów;
4. [`plans/PLAN_EXECUTION_HISTORY.md`](plans/PLAN_EXECUTION_HISTORY.md) — co planowano, co wdrożono, co zastąpiono i co zostało;
5. [`plans/CURRENT_STEP.md`](plans/CURRENT_STEP.md) — dokładny bieżący krok i kolejność dalszych prac;
6. [`project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`](project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md) — przekrojowe definicje i granice naukowe.

## Aktualne plany domenowe

- [`plans/LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`](plans/LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md) — finalne przywracanie/odbudowa/akceptacja pamięci;
- [`plans/AFFECT_ENGINE_CONVERGENCE_PLAN.md`](plans/AFFECT_ENGINE_CONVERGENCE_PLAN.md) — Emotion Engine / canonical affect;
- [`plans/V17_PLUS_SYSTEM_EVALUATION.md`](plans/V17_PLUS_SYSTEM_EVALUATION.md) — aktualna ocena systemu i warunkowy program v17+.

## Poprzednie plany

Cała poprzednia zawartość `docs/plans/` została zachowana w:

[`plans/only_to_check/`](plans/only_to_check/)

To materiał `ONLY_TO_CHECK / HISTORICAL_PLANNING_INPUT`. Stare `STATUS.md`, SHA, branch names i target versions zachowują wartość historyczną, ale nie są bieżącą prawdą.

## Project-wide — `docs/project/`

- `CURRENT_STATE.md` — bieżący overlay techniczny;
- `REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md` — role katalogów/entrypointów/dependencies;
- `PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md` — definicje Jaźni, pamięci, affect i granic;
- `RELEASE_TIMELINE.md` — release/decision index;
- `system-evaluation/` — datowane audyty/research snapshots; nie przepisywać ich po fakcie.

## Domain docs

- `docs/memory/` — Memory Rebuild, restore, recall, source fidelity;
- `docs/runtime/` — lifecycle, host/finalization/workspace;
- `docs/nlp/` — język i zasoby NLP;
- `docs/packaging/` — transport/package/attach;
- `docs/tools/` — aktywne narzędzia operatorskie;
- `docs/templates/` — acceptance/evidence templates.

## Historical — `docs/archive/`

Archiwum przechowuje zakończone/superseded raporty, plany, review, patche i stare narzędzia. Nie aktualizować snapshotów historycznych tak, aby wyglądały jak current docs.

## Zasada bieżącej prawdy

```text
aktualne AGENTS*
→ aktualny kod / testy / machine-readable evidence
→ aktualny master / PR / issue / CI
→ project/CURRENT_STATE.md
→ plans/PLAN_EXECUTION_HISTORY.md + CURRENT_STEP.md
→ plan domenowy
→ plans/only_to_check/
→ archive/
```

File/module presence, dawny zielony raport, nazwa brancha lub `ahead > 0` nie są samodzielnym dowodem `working/accepted/live`.

## Granica naukowa

System może implementować funkcjonalne appraisal, affect, homeostasis, replay, self-state i podobne kontrakty. Nie oznacza to biologicznego mózgu ani dowodu phenomenal consciousness. Wartość modułu wynika z evidence, causal effect, persistence i ablation — nie z antropomorficznej nazwy.
