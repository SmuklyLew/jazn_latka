# `docs/plans/only_to_check/` — wyłącznie historia i materiał kontrolny

**Status całego poddrzewa:** `HISTORICAL_ONLY / NON_AUTHORITATIVE`  
**Aktualizacja indeksu:** 2026-09-07

W tym katalogu znajdują się oryginalne stare plany, roadmapy, statusy, compatibility pointery, evidence snapshoty i poprzednie wersje dokumentacji planistycznej.

## Najważniejsza reguła

> Każdy status `ACTIVE`, `IN_PROGRESS`, `PLANNED`, `CURRENT`, numer mastera, branch, target release lub checklista zapisana **wewnątrz pliku w tym poddrzewie** jest historycznym stanem z chwili powstania dokumentu. Nie jest bieżącą instrukcją wykonawczą.

Bieżące źródła:

```text
../README.md
../V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md
../CURRENT_STEP.md
../PLAN_EXECUTION_HISTORY.md
../LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md
../AFFECT_ENGINE_CONVERGENCE_PLAN.md
../RESEARCH_EVIDENCE_BASE.md
../V17_PLUS_SYSTEM_EVALUATION.md
```

## Co tu zachowujemy

- `16.3.25.4-memory-rebuild-v4/` — oryginalny plan/status/evidence Memory Rebuild v4;
- `16.3.25.5.17-pack-generator-v101860/` — historyczny Pack Generator plan;
- `16.3.25.5.34-package-runtime-plugin-convergence/` — historyczny convergence plan;
- `16.3.26-attachment-ingress/` — pierwotny attachment roadmap;
- `16.4-to-16.6-cognitive-hardening/` — pierwotny cross-cutting plan;
- `16.6.0-final-convergence/` — dawna roadmapa final convergence;
- `17.0.0-measured-architecture-consolidation/` — dawny v17 planning snapshot;
- `2026-09-07-pr231-pre-memory-affect-rewrite/` — komplet aktywnych planów/pointerów istniejących po PR #231 przed obecną przebudową;
- pozostałe pliki — historyczne mapy, pointery i audyty.

## Jak odzyskiwać pominięte wymaganie

```text
historyczny fragment
→ sprawdzenie z current master/code/tests
→ klasyfikacja: nadal potrzebne / już wdrożone / superseded
→ przeniesienie samego wymagania do aktualnego owner planu
→ dodanie measurable acceptance
```

Nie cherry-pickować historycznego statusu, numeru wersji ani całej roadmapy tylko dlatego, że branch/dokument jest starym źródłem pomysłu.

## Granica naukowa

Historyczne antropomorficzne lub neuropsychologiczne nazwy nie są evidence biologicznej świadomości/emocji. Bieżące znaczenie terminów definiuje `docs/project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md` oraz aktualne plany.
