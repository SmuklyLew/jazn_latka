# `only_to_check` — snapshot poprzedniej mapy planów

**Przeniesiono:** 2026-09-07  
**Źródłowy master:** `378e9e6aceb83edbd679751e19cbe5c64c978025`  
**Źródłowa wersja:** `16.3.25.5.36-ci-archive-scope-contract-hardening`

Ten katalog zawiera **całą poprzednią zawartość `docs/plans/` przeniesioną bez utraty plików do jednego miejsca kontrolnego**.

Cel tej reorganizacji:

1. nie usuwać historycznych planów, statusów, pointerów i roadmap;
2. przestać traktować ich stare `STATUS.md`, transient SHA i dawne release numbers jako bieżącą prawdę;
3. umożliwić porównanie nowych planów kanonicznych z poprzednimi wymaganiami;
4. zachować provenance decyzji projektowych.

## Zasada użycia

Pliki w tym katalogu są materiałem **`ONLY_TO_CHECK / HISTORICAL_PLANNING_INPUT`**. Nie są aktywnymi właścicielami bieżącego statusu.

Bieżącą kolejność pracy określają pliki znajdujące się bezpośrednio w `docs/plans/`, przede wszystkim:

- `README.md`;
- `PLAN_EXECUTION_HISTORY.md`;
- `CURRENT_STEP.md`;
- `LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`;
- `AFFECT_ENGINE_CONVERGENCE_PLAN.md`;
- `V17_PLUS_SYSTEM_EVALUATION.md`.

Dla statusów `implemented`, `merged`, `working`, `verified`, `accepted`, `live` obowiązuje kolejność dowodu:

```text
AGENTS* + aktualny kod/testy/machine-readable evidence
→ aktualny master / PR / issue / CI
→ docs/project/CURRENT_STATE.md
→ aktywne nowe docs/plans
→ ten katalog only_to_check
→ docs/archive
```

Stary plan nie zostaje „naprawiony po fakcie”. Jeśli jego cel został zrealizowany później, lepiej albo pod innym numerem release, stan ten jest opisany w `PLAN_EXECUTION_HISTORY.md` z odwołaniem do rzeczywistego wdrożenia.
