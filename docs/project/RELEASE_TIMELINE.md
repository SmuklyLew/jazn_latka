# Release timeline / decision index

**Aktualizacja:** 2026-09-07  
**Current snapshot:** `master @ 378e9e6aceb83edbd679751e19cbe5c64c978025` / `16.3.25.5.36-ci-archive-scope-contract-hardening`

Ten dokument jest indeksem ewolucji systemu. Szczegółowe historyczne raporty pozostają w `docs/archive/`; bieżące plany i status są w `docs/plans/`.

## Statusy

- `CURRENT` — bieżący master snapshot;
- `MERGED` — zakres dostarczony na master;
- `SUPERSEDED` — rozwiązanie/plan zastąpiony nowszym kontraktem;
- `OPEN` — nadal wymagany w bieżącym programie;
- `FUTURE` — warunkowy po wcześniejszych gates.

## Główne etapy

| Linia | Status | Znaczenie |
|---|---|---|
| v15.4.x | MERGED / historical | task continuity, bounded reasoning, finalization continuity, Rest/Replay/Dream truth boundaries, evidence ladder |
| v15.5 | MERGED / historical | local-first memory; cloud jako transport/durability |
| v16.0.x | MERGED / historical | persistent runtime, liveness, host-finalization lifecycle |
| v16.1.x | MERGED / historical | epistemic gates, offline rest, unified memory foundations |
| v16.2.x | MERGED / historical | cognitive-state policy, process isolation, measured retrieval experiments |
| v16.3.0–21 | MERGED / historical | Memory Rebuild Studio, host fallback, memory/runtime convergence |
| v16.3.22 | MERGED | requested root != subject root; A/B/B identity gate |
| v16.3.23 | MERGED | persistent lifecycle / pre-response / recall E2E |
| v16.3.24 | MERGED | package provenance/bootstrap hardening |
| v16.3.25 | MERGED | Memory Rebuild source-union hardening |
| v16.3.25.1 | MERGED | host-finalization gate / next-turn lifecycle |
| v16.3.25.2 | MERGED | live Voice readiness contract |
| v16.3.25.3 | MERGED | schema/release metadata semantics |
| v16.3.25.3.3–.6 | MERGED | package discovery, Pack Generator v8.7 era, AGENTS/startup convergence |
| **v16.3.25.4** | **MERGED** | Memory Rebuild v4 consolidation; PR #208; #189 closed |
| v16.3.25.5 | MERGED | package distribution convergence |
| v16.3.25.5.5–.14 | MERGED | distribution/Pack Generator/RAR/CI hardening |
| v16.3.25.5.16 | MERGED | verified Python runtime bundle + CI hardening; PR #213 |
| v16.3.25.5.17–.18 | MERGED | Pack Generator 10.1.86.0 line + lock persistence/dependency work |
| v16.3.25.5.19 | MERGED | Pack Generator 10.1.86.0 + Pyright hardening; PR #215 |
| v16.3.25.5.20–.27 | MERGED | Pylance/archive, bundle health, Windows smoke, byte-exact/EOL, folder snapshot; generator up to .113 |
| v16.3.25.5.28–.29 | MERGED | runtime-first ChatGPT handoff + release metadata/operator convergence |
| v16.3.25.5.30 | MERGED | GitHub Actions Node24/tooling convergence |
| v16.3.25.5.31–.33 | MERGED | host-executor truth boundary, recovery and CI convergence |
| v16.3.25.5.34 | MERGED | package-runtime-plugin convergence; canonical SYSTEM staging; generator 10.1.86.0.114 |
| v16.3.25.5.35 | MERGED | Pylance optional-contract hardening |
| **v16.3.25.5.36** | **CURRENT** | CI archive scope / declared archive-extra convergence |
| attachment/multimodal stage | OPEN | poprzednio planowane jako v16.3.26; numer przyszłego release ustali fresh master |
| Polish NLP stage | OPEN | evidence-aware normalization/resources/query evidence |
| final private memory #59 | OPEN | VERIFIED → ATTACHABLE → RETRIEVABLE → ACCEPTED |
| Emotion Engine / affect convergence | OPEN | canonical affect state, persistence, causal effects, measured memory integration |
| v16.6 final evidence gate | FUTURE in current program | runtime/memory/NLP/affect/cognitive/governance convergence |
| v17+ | FUTURE / CONDITIONAL | measured architecture consolidation po v16.6 evidence |

## Memory Rebuild v4 — korekta dawnego timeline

Dawny indeks pokazywał `v16.3.25.4 = ACTIVE`. To było prawdziwe 2026-09-01, ale przestało być aktualne po:

```text
PR #208 merge
→ 601cf3fe977621c5552f7f6e32530da0128ccc8a
→ release metadata sync a8b5fa4...
→ issue #189 CLOSED
```

Dzisiejszy status: `MERGED`.

Finalna prywatna pamięć nie została tym samym zamknięta; nadal należy do #59.

## Dlaczego pojawiła się długa linia 16.3.25.5.x

Pierwotna roadmapa zakładała przejście po Memory Rebuild wprost do attachment/NLP/final memory. Rzeczywisty system wymagał najpierw rozbudowanego hardeningu:

- package/distribution;
- generator integrity i portable staging;
- Python/dependency contracts;
- static analysis/CI;
- host/executor truth/recovery;
- plugin/optional capability boundaries.

Te prace nie anulują późniejszych celów. Zmieniły **fundament i numerację**, dlatego przyszłych numerów nie wolno przydzielać mechanicznie z dawnych dokumentów.

## Bieżący plan execution

Zobacz:

- `docs/plans/PLAN_EXECUTION_HISTORY.md` — pełna konwergencja planów/statusów;
- `docs/plans/CURRENT_STEP.md` — aktualna kolejność;
- `docs/plans/LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`;
- `docs/plans/AFFECT_ENGINE_CONVERGENCE_PLAN.md`;
- `docs/plans/V17_PLUS_SYSTEM_EVALUATION.md`.

Poprzednie `docs/plans/` zostały zachowane w `docs/plans/only_to_check/`.

## Historyczne źródła evidence

- `docs/archive/plans/`;
- `docs/archive/roadmaps/`;
- `docs/archive/reports/`;
- `docs/archive/reviews/`;
- `docs/archive/patches/`;
- `docs/archive/tools/`;
- `docs/archive/chatgpt_host_legacy/`.

Historyczny FAIL/NOT RUN/rollback pozostaje częścią decision logu i nie jest poprawiany po fakcie.

## Zasada promowania historii

```text
history finding
→ current invariant
→ current code gap
→ regression / measurable hypothesis
→ implementation on fresh current line
→ focused + full validation
→ current report
```

Nie wykonywać blind cherry-picków tylko dlatego, że dawny branch jest `ahead`.
