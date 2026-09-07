# Release timeline / decision index

**Aktualizacja:** 2026-09-07  
**Current master baseline:** `e828c2f4ab10a909d9d8b2324e69caf68f82c94d` / `16.3.25.5.38-ci-release-fixture-isolation`  
**Current documentation branch target:** `16.3.25.5.39-memory-affect-docs-convergence`

Ten dokument jest indeksem ewolucji. Historyczne raporty/patches/hotfixes pozostają w `docs/archive/`; bieżące wykonanie opisuje `docs/plans/`.

## Statusy

- `CURRENT_MASTER` — faktyczny master snapshot z nagłówka.
- `IN_PR_BRANCH` — zmiana przygotowywana na branchu, jeszcze nie master.
- `MERGED` — dostarczone.
- `SUPERSEDED` — zastąpione nowszym kontraktem.
- `OPEN` — nadal wymagane.
- `FUTURE_CONDITIONAL` — po wcześniejszych gates.

## Główna historia do bieżącego programu

| Linia | Status | Znaczenie |
|---|---|---|
| v15.4–v16.2 | MERGED / historical | continuity, epistemic gates, unified-memory/cognitive foundations, process isolation, measured retrieval/rest foundations |
| v16.3.0–21 | MERGED / historical | Memory Rebuild Studio + host/memory/runtime convergence |
| v16.3.22 | MERGED | root/subject identity gate |
| v16.3.23 | MERGED | persistent lifecycle/pre-response/recall E2E |
| v16.3.24 | MERGED | package provenance/bootstrap hardening |
| v16.3.25 | MERGED | Memory Rebuild source-union hardening |
| v16.3.25.1–.3 | MERGED | finalization, voice readiness, schema/release semantics |
| **v16.3.25.4** | **MERGED** | Memory Rebuild v4 consolidation; PR #208; #189 closed |
| v16.3.25.5–.14 | MERGED | package distribution / Pack Generator / RAR / CI hardening |
| v16.3.25.5.16–.19 | MERGED | verified Python runtime bundle, generator/Pyright/dependency hardening |
| v16.3.25.5.20–.27 | MERGED | Pylance/archive, bundle health, Windows smoke, byte-exact/EOL, folder snapshot |
| v16.3.25.5.28–.33 | MERGED | ChatGPT runtime-first handoff, metadata/operator, Node24, host-executor truth/recovery |
| v16.3.25.5.34 | MERGED | package-runtime-plugin convergence; canonical SYSTEM staging |
| v16.3.25.5.35 | MERGED | Pylance optional contracts |
| v16.3.25.5.36 | MERGED | CI archive scope / declared archive extras |
| v16.3.25.5.37 | MERGED in branch ancestry/history | clean release fixture/related canonical release hardening predecessor |
| **v16.3.25.5.38** | **CURRENT_MASTER** | install declared PowerShell-regression extras + isolate canonical release packaging tests from CI metadata materialization |
| **v16.3.25.5.39** | **IN_PR_BRANCH** | documentation-only Memory/Affect roadmap convergence; no runtime behavior change |

## PR #231

`MERGED` 2026-09-07.

Cel: pierwsza duża konwergencja planów, nowe Memory/Affect/V17 docs i przeniesienie starej roadmapy do `only_to_check/`.

Post-merge pozostały stale current-state refs `.36 / 378e9e6...` oraz compatibility pointers w root `docs/plans/`. `.39` domyka te braki i zachowuje snapshot PR #231 przed rewrite.

## Otwarte workstreams po `.39`

| Workstream | Status | Gate |
|---|---|---|
| attachment/multimodal | OPEN | provenance + safe staging + capability routing + E2E |
| Polish NLP evidence | OPEN | context/negation/ambiguity/resource provenance |
| final private memory #59 | OPEN | VERIFIED → ATTACHABLE → RETRIEVABLE → ACCEPTED |
| Affect E0 inventory | OPEN / can start early | shadow-only, zero visible behavior change |
| canonical Affect Engine | OPEN | one state authority + persistence + causal effect + ablation |
| Memory↔Affect rerank | BLOCKED UNTIL BASELINE | frozen private Recall first; then SHADOW→A/B |
| bounded resonance | BLOCKED UNTIL GATES | MemoryUseGate + A/B + one-pass bound |
| v16.6 | FUTURE | full evidence package |
| v17 | FUTURE_CONDITIONAL | only after v16.6 PASS |

## Zasada numeracji

Historyczne targety `16.3.26`, `16.4`, `16.5`, `16.6`, `17.0` są logicznymi markerami programu. Rzeczywisty implementation release zawsze ustala numer z fresh master i aktualnej polityki versioning. Nie cofać wersji ani nie rezerwować numeru na podstawie starego planu.

## Historia planów/patchy/hotfixów

- aktywne plany: `docs/plans/`;
- historyczne/planning snapshots: `docs/plans/only_to_check/`;
- stare release plans/reports/patches/hotfix reviews: `docs/archive/` i jego domenowe podkatalogi.

`ACTIVE`, `IN_PROGRESS` lub target branch wewnątrz `only_to_check/`/`archive/` jest historyczną treścią. Nie jest bieżącym statusem.

## Reguła promowania historycznego wymagania

```text
history finding
→ verify against current master
→ current invariant/gap
→ measurable hypothesis
→ implementation on fresh branch
→ tests/A-B/ablation
→ current report
```

Nie wykonywać blind cherry-picków starego brancha ani całej roadmapy tylko dlatego, że zawiera wartościowy fragment.
