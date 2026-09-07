# Project-wide documents

**Aktualizacja mapy:** 2026-09-07

Ten katalog zawiera wyłącznie przekrojowe kontrakty projektu, bieżący state overlay oraz datowane audyty/reference. Nie jest drugą powierzchnią aktywnych roadmap.

## Bieżące źródła

- [`CURRENT_STATE.md`](CURRENT_STATE.md) — bieżący overlay rzeczywistego stanu projektu;
- [`PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`](PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md) — kanoniczny słownik, source hierarchy i granice naukowe;
- [`RELEASE_TIMELINE.md`](RELEASE_TIMELINE.md) — bieżący indeks historii wydań i otwartych workstreams;
- [`REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md`](REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md) — przekrojowa polityka layout/dependencies.

## Datowane audyty — `HISTORICAL_REFERENCE`

- [`PLAN_COHERENCE_AUDIT_2026-08-30.md`](PLAN_COHERENCE_AUDIT_2026-08-30.md);
- [`REPOSITORY_CONVERGENCE_AUDIT_2026-09-01.md`](REPOSITORY_CONVERGENCE_AUDIT_2026-09-01.md).

Datowany audyt zachowuje stan wiedzy z chwili powstania. `ACTIVE`, `IN_PROGRESS`, SHA, branch, target release albo ocena planu wewnątrz takiego dokumentu nie jest bieżącym statusem.

## Aktywne plany są tylko w `docs/plans/`

Kolejność wykonania należy wyłącznie do:

- [`../plans/README.md`](../plans/README.md);
- [`../plans/V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md`](../plans/V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md);
- [`../plans/CURRENT_STEP.md`](../plans/CURRENT_STEP.md);
- [`../plans/PLAN_EXECUTION_HISTORY.md`](../plans/PLAN_EXECUTION_HISTORY.md);
- [`../plans/LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`](../plans/LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md);
- [`../plans/AFFECT_ENGINE_CONVERGENCE_PLAN.md`](../plans/AFFECT_ENGINE_CONVERGENCE_PLAN.md);
- [`../plans/RESEARCH_EVIDENCE_BASE.md`](../plans/RESEARCH_EVIDENCE_BASE.md);
- [`../plans/V17_PLUS_SYSTEM_EVALUATION.md`](../plans/V17_PLUS_SYSTEM_EVALUATION.md).

## Dawne `project/system-evaluation/`

Poprzednia v16.6→v17 evaluation wraz z DOCX i research addendum została przeniesiona bez zmiany treści do:

`../plans/only_to_check/2026-09-07-pr231-pre-memory-affect-rewrite/project-system-evaluation/`

Powód: po ustanowieniu nowej kanonicznej v16.3.25.4→v17 roadmapy pozostawienie starej evaluation obok bieżących dokumentów tworzyłoby drugą, konkurencyjną powierzchnię planistyczną.

## Zasada aktualności

`CURRENT_STATE.md` i `RELEASE_TIMELINE.md` mogą być aktualizowane wraz z masterem. Datowanych audytów nie przepisywać po fakcie; jeśli wymaganie nadal jest ważne, zweryfikować je względem current master i włączyć do aktualnego owner planu z mierzalnym acceptance.

Dokument projektowy nie certyfikuje własnego `PASS`, `MERGED`, `VERIFIED`, `ACCEPTED` ani aktywnego runtime.
