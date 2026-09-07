# Jaźń — PLAN EXECUTION HISTORY v16.3.25.4 → v17

**Status:** `CANONICAL_EXECUTION_HISTORY`  
**Aktualizacja:** 2026-09-07  
**Baza przebudowy dokumentacji:** `master @ e828c2f4ab10a909d9d8b2324e69caf68f82c94d` / `16.3.25.5.38-ci-release-fixture-isolation`

Ten dokument zapisuje historię decyzji bez przepisywania przeszłości. Historyczne plany/statusy pozostają w `only_to_check/`; tutaj utrzymujemy wyłącznie ich aktualną klasyfikację względem bieżącego mastera.

## Statusy

- `MERGED` — cel dostarczony w deklarowanym zakresie.
- `OPEN` — nadal wymagany.
- `SUPERSEDED` — cel został zrealizowany inaczej lub nowszy kontrakt go zastąpił; nie wykonywać starego planu literalnie.
- `HISTORICAL_ONLY` — dowód wcześniejszego stanu, nie active plan.
- `FUTURE_CONDITIONAL` — wejście dopiero po gate.

---

# 1. v16.3.25.4 — Memory Rebuild v4 consolidation

**Status:** `MERGED`.

Evidence:

```text
PR #208 merged 2026-09-02
merge commit 601cf3fe977621c5552f7f6e32530da0128ccc8a
issue #189 closed
```

Dostarczony zakres:

- jeden `ProtocolEngine/ApplicationService` i `memory_rebuild_app`;
- Test00→Final;
- source fidelity / RAW-L0 / provenance;
- source-monitoring i primary-vs-derived hierarchy;
- reproducibility;
- real private Test04 runner z `NOT RUN` przy braku private dataset;
- final SQLite snapshot validation;
- brak automatic L2/L3 i brak auto-activation.

Nie dostarczono celowo finalnej private memory acceptance. To pozostaje #59.

Stare `IN_PROGRESS`, „PR not merged” i aktywny branch dla tego etapu są `HISTORICAL_ONLY`.

---

# 2. v16.3.25.5.x — foundation hardening

**Status:** `MERGED` do `.38` w zakresie aktualnego mastera.

Rzeczywista historia dodała między v16.3.25.4 a dalszymi etapami m.in.:

- package/distribution convergence;
- Pack Generator 10.1.86.0 line i kolejne integrity hardeningi;
- byte-exact/EOL/folder/canonical SYSTEM release staging;
- Python runtime/dependency contracts;
- Pylance/Pyright/CI archive scope;
- ChatGPT runtime-first host handoff;
- host/executor truth + bounded recovery;
- Node24 Actions/tooling convergence;
- package/runtime/plugin convergence;
- clean release fixture isolation w `.38`.

Historyczne plany generatora v8.x/v10.0.1 i sztywne oczekiwanie „po 16.3.25.4 natychmiast 16.3.26” są `SUPERSEDED` jako numeracja/implementation prescription. Ich cele funkcjonalne są rozliczane względem aktualnego kodu.

---

# 3. PR #231 — pierwsza konwergencja planów

**Status:** `MERGED`, commit merge `13ed78c5eee45725e38d4223353a1e45ff34f4f3`, po którym master otrzymał release metadata sync `.38`.

PR #231:

- ustanowił `CURRENT_STEP`, `PLAN_EXECUTION_HISTORY`, Memory/Affect/V17 docs;
- przeniósł większość poprzednich planów do `only_to_check/`;
- poprawił rozróżnienie active vs historical.

Pozostały jednak:

- compatibility pointery nadal widoczne w root `docs/plans/`;
- stale snapshot metadata `.36 / 378e9e6...`;
- brak jednego nadrzędnego Memory↔Affect roadmap;
- brak osobnego canonical research/evidence register;
- kilka wymagań Emotion Engine v0.2 niewyrażonych jawnie w v1.

Bieżąca `.39` documentation convergence usuwa te braki. Snapshot po PR #231 jest zachowany w `only_to_check/2026-09-07-pr231-pre-memory-affect-rewrite/`.

---

# 4. Historyczne attachment/multimodal plans

**Status celu:** `OPEN`.  
**Status dawnych dokumentów:** `HISTORICAL_ONLY`.

Cel pozostaje:

```text
attachment-only / text+attachment / multi-attachment
exact identity + provenance
safe bounded staging
MIME/type/extraction policy
capability-driven vision/audio
external content = untrusted data
no automatic memory/tool authority
```

Finalny numer implementacji ustala fresh master; historyczne `v16.3.26` jest markerem pierwotnej roadmapy, nie rezerwacją numeru.

---

# 5. Historyczne v16.4–v16.6 cognitive hardening plans

**Status dawnych dokumentów:** `HISTORICAL_ONLY / SUPERSEDED AS ACTIVE ROADMAP`.

Wymagania zostały rozdzielone do aktualnych owners:

```text
program sequence → V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md
current action → CURRENT_STEP.md
memory → LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md
affect → AFFECT_ENGINE_CONVERGENCE_PLAN.md
research → RESEARCH_EVIDENCE_BASE.md
v17 → V17_PLUS_SYSTEM_EVALUATION.md
```

Nie przywracać starej monolitycznej roadmapy jako równoległej authority.

---

# 6. Final private memory / issue #59

**Status:** `OPEN / CENTRAL`.

Pozostała droga:

```text
source inventory freeze
→ rebuild/Test00–04
→ VERIFIED
→ memory package + canonical attach
→ ATTACHABLE
→ frozen Recall baseline
→ RETRIEVABLE candidate
→ measured fixes if required
→ manual review + restart continuity
→ ACCEPTED candidate
→ v16.6 final acceptance
```

Memory Rebuild tool merge nie zamyka #59.

---

# 7. Emotion Engine / Affect convergence

**Status:** `PLAN READY / IMPLEMENTATION NOT STARTED` poza istniejącymi legacy foundations.

Historyczny branch `plan/v16.4-affective-memory-convergence` zawiera Emotion Engine v0.2 i jest `HISTORICAL_ONLY`, nie implementation base.

Wartościowe wymagania odzyskane z v0.2 do v2:

- jawne referencje affect w `CognitiveTurnEnvelope`;
- brak nowego globalnego EventBus;
- quarantine/diagnostics przy corrupted affect persistence;
- pełniejsze CI/cross-platform/persistent-E2E requirements;
- jawne bounded memory-importance/reflection/replay modulation, nigdy truth status;
- obowiązek synchronizacji implementowanych mechanizmów z `scientific_basis.py`.

Cel v2:

```text
one AffectiveStateIntegrator
one AffectiveStateV2
EvidenceRef + AppraisalV2
FeelingRepresentation derived
accepted-turn atomicity
SelfState/Homeostasis/Salience bounded effects
affect snapshot lineage
affective rerank SHADOW→A/B after frozen memory baseline
one-pass resonance
ablation + false-memory non-regression
```

---

# 8. Polish NLP evidence

**Status:** `OPEN / PREREQUISITE`.

Canonical semantic affect activation wymaga evidence contract obejmującego polską normalizację, ambiguity/OOV, negation, quotation/fiction, context, referential/temporal evidence i lexical-resource provenance.

Nowe badania LLM nad contextual/cultural emotion reasoning wzmacniają wymóg testowania poza keyword recognition; są jednak tylko research guidance, nie implementacją.

---

# 9. Memory ↔ Affect integration

**Status:** `OPEN / ORDERED`.

Możliwe wcześniej:

```text
Affect A0 inventory/shadow
affect snapshot schema linkage przy accepted episode
```

Wymagające frozen memory baseline:

```text
affective rerank visible effect
A/B acceptance
bounded resonance
```

Twarde invariants:

```text
affect != source truth
similarity != identity
no source -> abstain
no accepted turn -> no durable affect commit
resonance only after MemoryUseGate
```

---

# 10. v16.6

**Status:** `FUTURE IN CURRENT PROGRAM / EVIDENCE GATE`.

Nie jest osobnym wielkim refactorem. Musi zebrać evidence dla runtime/host, attachments, NLP, accepted memory, canonical affect, source monitoring, cognitive ablation, Rest/Dream utility/safety, model capability/context, package integrity, cross-platform CI i governance.

---

# 11. v17

**Status:** `FUTURE_CONDITIONAL`.

Nie implementować przed v16.6 PASS.

Kierunek:

```text
measured CausalSelfState consolidation
bounded context compiler
capability-driven model routing
source-aware reversible reconsolidation/forgetting
calibrated metacognition or ordinal support
measured retrieval evolution
module keep/merge/remove by ablation
authority/policy simplification
```

---

# 12. Historia dokumentów

W `docs/plans/only_to_check/` znajdują się:

- oryginalne katalogi Memory Rebuild v4, attachment, cognitive hardening, v16.6 i v17;
- stare Pack Generator planning snapshots;
- compatibility aliases/pointers;
- PR #231 pre-rewrite snapshot;
- historyczne statusy/evidence.

Zasada:

```text
old document finding
→ verify against current master
→ extract requirement with provenance
→ place in current owner document
→ add measurable acceptance
```

Nie aktualizować historycznego pliku tak, aby wyglądał na bieżący.
