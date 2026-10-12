# Jaźń — kanoniczna mapa planów

**Aktualizacja:** 2026-09-07  
**Zweryfikowana baza:** `master @ 378e9e6aceb83edbd679751e19cbe5c64c978025`  
**Wersja bazowa:** `16.3.25.5.36-ci-archive-scope-contract-hardening`

Ten katalog został uporządkowany po audycie planów od `JAZN_V16_3_25_4` do `JAZN_V16_6_TO_V17` oraz rzeczywistych wdrożeń, które trafiły później do `master`.

## Aktywne dokumenty

| Dokument | Rola |
|---|---|
| [`PLAN_EXECUTION_HISTORY.md`](PLAN_EXECUTION_HISTORY.md) | jeden przebieg dawnych planów, rzeczywistych wdrożeń, zmian kolejności i checklisty statusu |
| [`CURRENT_STEP.md`](CURRENT_STEP.md) | jednoznacznie: gdzie jesteśmy teraz i jaka jest następna kolejność prac |
| [`LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`](LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md) | aktualny plan przywrócenia/odbudowy i finalnej akceptacji pamięci Łatki |
| [`AFFECT_ENGINE_CONVERGENCE_PLAN.md`](AFFECT_ENGINE_CONVERGENCE_PLAN.md) | aktualny kanoniczny subplan Emotion Engine / affect / feeling |
| [`V17_PLUS_SYSTEM_EVALUATION.md`](V17_PLUS_SYSTEM_EVALUATION.md) | zaktualizowana ocena systemu i warunkowy program v17+ |
| [`only_to_check/`](only_to_check/) | pełna poprzednia zawartość `docs/plans/`, zachowana jako materiał historyczny/kontrolny |

## Hierarchia prawdy

```text
AGENTS* + aktualny kod/testy/machine-readable evidence
        ↓
aktualny master / PR / issue / CI
        ↓
docs/project/CURRENT_STATE.md
        ↓
PLAN_EXECUTION_HISTORY.md + CURRENT_STEP.md
        ↓
plan domenowy: memory / affect / v17
        ↓
only_to_check/
        ↓
docs/archive/
```

Żaden dokument planistyczny nie certyfikuje własnego `PASS`.

## Najkrótszy status

- 🟢 `16.3.25.4 Memory Rebuild v4 consolidation` — **MERGED**; PR #208, issue #189 closed. Narzędzie/protokół Test00→Final jest fundamentem bieżącego systemu.
- 🟢 kolejne hardeningi linii `16.3.25.5.x` — package/distribution, Pack Generator, Python runtime/dependency contracts, host/executor truth, CI i plugin/runtime convergence zostały dostarczone na master do `16.3.25.5.36`.
- 🟡 finalna prywatna pamięć — **nie jest jeszcze ACCEPTED**; issue #59 pozostaje otwarte.
- 🟡 `attachment + multimodal ingress` — nadal do implementacji jako osobny etap.
- 🟡 evidence-aware Polish NLP — nadal do implementacji przed pełną semantyczną aktywacją nowego affect appraisal.
- 🟡 Emotion Engine / affect convergence — nowy kanoniczny plan jest gotowy; implementacja ma być etapowa i pomiarowa.
- ⚪ v17 — nadal `FUTURE / CONDITIONAL`; nie wdrażać przed v16.6 evidence gate.

## Zasada numeracji

Historyczne numery z dawnych roadmap są **kolejnością logiczną, nie rezerwacją numeru za wszelką cenę**. Aktualny master przeszedł przez wiele koniecznych hardeningów `16.3.25.5.x`; dlatego każdy przyszły branch zaczyna z fresh master i dopiero wtedy ustala legalny numer wersji.

## Granica naukowa

Jaźń jest projektowana jako trwała, source-aware i truth-bounded architektura agenta. Terminy `emotion`, `feeling`, `homeostasis`, `neurocognitive`, `dream` i podobne opisują funkcjonalne kontrakty software. Nie są dowodem biologicznych procesów ani phenomenal consciousness.
