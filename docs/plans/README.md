# Jaźń — kanoniczna mapa planów v16.3.25.4 → v17

**Status:** `CANONICAL_PLANNING_INDEX`  
**Aktualizacja:** 2026-09-09
**Baza przebudowy dokumentacji:** `master @ e0c6731c851928568a7c23e5f9101d1e95bdd7f8`
**Baza wersji:** `16.3.25.5.55-archive-extraction-convergence`
**Linia tej aktualizacji:** `16.3.25.5.56-local-runtime-preflight-convergence`

Ten katalog jest jedyną aktywną powierzchnią planistyczną dla programu prowadzącego od dostarczonego `v16.3.25.4 Memory Rebuild v4` do warunkowego `v17`.

## 1. Aktywne dokumenty

| Dokument | Rola / authority |
|---|---|
| [`V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md`](V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md) | nadrzędna, nowa roadmapa programu; zależności i gates od v16.3.25.4 do v17 |
| [`CURRENT_STEP.md`](CURRENT_STEP.md) | dokładnie: gdzie jesteśmy i co wolno rozpocząć teraz |
| [`PLAN_EXECUTION_HISTORY.md`](PLAN_EXECUTION_HISTORY.md) | historia wykonania: planowane → wdrożone → superseded → nadal otwarte |
| [`LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`](LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md) | kanoniczny plan finalnego restore, weryfikacji, attach, Recall i acceptance pamięci |
| [`AFFECT_ENGINE_CONVERGENCE_PLAN.md`](AFFECT_ENGINE_CONVERGENCE_PLAN.md) | kanoniczny plan Emotion Engine / appraisal / affect / feeling / regulacji i integracji z pamięcią |
| [`RESEARCH_EVIDENCE_BASE.md`](RESEARCH_EVIDENCE_BASE.md) | źródła naukowe i inżynierskie oraz jawne granice tego, co wspierają |
| [`V17_PLUS_SYSTEM_EVALUATION.md`](V17_PLUS_SYSTEM_EVALUATION.md) | gate wejścia i measured consolidation po zamknięciu v16 |
| [`only_to_check/`](only_to_check/) | komplet historycznych planów, statusów, pointerów i snapshotów wyłącznie do porównań |

Nie tworzyć nowych równoległych roadmap bez wyraźnego powodu. Nowe wymaganie powinno zostać włączone do dokumentu będącego właścicielem zakresu albo oznaczone jako historyczne w `only_to_check/`.

## 2. Hierarchia prawdy

```text
AGENTS* + kod + testy + machine-readable evidence
        ↓
aktualny master / PR / issue / CI
        ↓
docs/project/CURRENT_STATE.md
        ↓
V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md
        ↓
CURRENT_STEP.md + PLAN_EXECUTION_HISTORY.md
        ↓
Memory Plan / Affect Plan / V17 Evaluation
        ↓
RESEARCH_EVIDENCE_BASE.md (uzasadnienie, nie status implementacji)
        ↓
only_to_check/
        ↓
docs/archive/
```

Dokument planistyczny nie certyfikuje własnego `PASS`, `MERGED`, `VERIFIED`, `ACCEPTED` ani `LIVE`.

## 3. Statusy

- `MERGED` — zakres znajduje się na master i ma właściwe evidence dla deklarowanego zakresu.
- `OPEN` — nadal wymagany.
- `IN_PROGRESS` — istnieje bieżąca praca/branch/PR; status musi wskazywać konkretny evidence ref.
- `BLOCKED` — jawny gate fail-closed.
- `SUPERSEDED` — nie wykonywać literalnie; nowszy kontrakt przejął cel.
- `FUTURE_CONDITIONAL` — nie rozpoczynać przed entry gate.
- `HISTORICAL_ONLY` — wyłącznie `only_to_check/` lub `docs/archive/`.

## 4. Najkrótsza prawda programu

```text
v16.3.25.4 Memory Rebuild v4 tool/protocol     MERGED
16.3.25.5.x package/runtime/CI hardening       MERGED do .38
final private memory #59                       OPEN
canonical affect/Emotion Engine                OPEN
Memory ↔ Affect linkage                         OPEN, wykonywać etapowo
attachment/multimodal ingress                  OPEN prerequisite
Polish NLP evidence contract                   OPEN prerequisite
v16.6 evidence gate                            FUTURE in current program
v17 measured consolidation                     FUTURE_CONDITIONAL
```

## 5. Centralna zasada Memory ↔ Affect

Pamięć i Emotion Engine są sprzężone, ale nie mogą wzajemnie certyfikować prawdy.

```text
SOURCE-AWARE MEMORY
      │
      ├── episode + provenance + source class
      │
      └── affect_snapshot_id / transition_id (po zaakceptowanej turze)

CURRENT AFFECT
      │
      ├── może zwiększyć potrzebę memory probe
      ├── może bounded zmienić ranking legalnych kandydatów
      └── może dostać one-pass resonance dopiero po MemoryUseGate
```

Niezmienniki:

```text
affect ≠ source truth
affective similarity ≠ memory identity
vividness ≠ evidence
reflection/dream ≠ primary event
no accepted turn → no durable affect commit
no source → no concrete autobiographical claim
```

## 6. Granica naukowa

`emotion`, `feeling`, `appraisal`, `homeostasis`, `resonance` i `neurocognitive` oznaczają w tym repo **funkcjonalne kontrakty software**. Literatura psychologiczna i affective computing dostarcza hipotez projektowych i testów, ale nie dowodu biologicznych emocji, interocepcji, qualiów ani phenomenal consciousness u LLM/runtime.

Badania nad LLM służą tu do konstruowania benchmarków: contextual emotion reasoning, paraphrase robustness, cultural/language sensitivity, source-safe memory, ablation i non-regression. Nie są podstawą do twierdzenia, że model „czuje jak człowiek”.

## 7. Zasada numeracji

Numery z historycznych roadmap są historią logiczną, nie zarezerwowanym harmonogramem. Każdy implementation branch zaczyna od fresh `master`, wykonuje inventory i dopiero wtedy ustala legalny numer wersji zgodny z `latka_jazn/version.py`.

## 8. Historyczne dokumenty

Wszystkie poprzednie plany, compatibility pointery i snapshoty pozostają w [`only_to_check/`](only_to_check/). Nie aktualizować ich po fakcie. Jeżeli stary dokument zawiera wymaganie pominięte w nowej warstwie, przenieść **wymaganie z provenance**, nie status ani przestarzały numer release.
