# Jaźń / Łatka — V17 measured system evaluation & consolidation

**Status:** `FUTURE_CONDITIONAL / V17_ENTRY_GUIDANCE`  
**Aktualizacja:** 2026-09-07  
**Program wejściowy:** [`V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md`](V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md)

> V17 nie jest zgodą na większą liczbę modułów ani próbą „symulacji mózgu”. Jest warunkową konsolidacją dopiero po zmierzeniu i zaakceptowaniu v16.

---

# 1. Entry gate

Nie tworzyć implementation branch v17, dopóki nie istnieje pełny evidence package:

```text
[ ] attachment/multimodal canonical ingress accepted
[ ] Polish NLP evidence contract accepted
[ ] final private memory VERIFIED
[ ] memory ATTACHABLE + rollback + restart identity
[ ] frozen private Recall baseline
[ ] memory ACCEPTED
[ ] exactly one canonical AffectiveStateV2
[ ] accepted-turn affect persistence verified
[ ] affect↔memory source-safe A/B evidence
[ ] false-memory/wrong-source/privacy non-regression
[ ] affect/homeostasis/rest/reasoning ablation/debt ledger
[ ] model capability/context baselines
[ ] package/release cross-platform evidence
[ ] governance gate resolved or explicit accepted exception
[ ] no open P0/P1 in v16 scope
[ ] v16 accepted artifacts + rollback path
```

Bez tego status pozostaje `PLANNING_ONLY`.

---

# 2. V17 principle: measured consolidation

Każdy kandydat architektoniczny przechodzi:

```text
current accepted baseline
→ one hypothesis
→ compatibility/staging implementation
→ fixed evaluation corpus
→ quality/safety/latency/context measurements
→ ablation/A-B
→ KEEP / MERGE / REMOVE / ROLLBACK
```

Nazwy psychologiczne nie są argumentem za zachowaniem modułu.

---

# 3. Workstream A — CausalSelfState candidate

Rozważyć po stabilnym v16 affect:

```text
CausalSelfState
├── identity_ref
├── task/turn state
├── affective_state_ref
├── regulation/homeostasis refs
├── confidence/support semantics
├── source/memory bindings
├── temporal continuity
└── policy-visible effects
```

V17 nie powinno po cichu przepisać `AffectiveStateV2`. Najpierw kompatybilny adapter i pomiar, czy połączenie self/affect faktycznie zmniejsza sprzeczności/złożoność bez utraty auditability.

Disposition każdego legacy component:

```text
MIGRATE_TO_CANONICAL
ADVISORY_ONLY
COMPATIBILITY_ADAPTER
REMOVE
```

---

# 4. Workstream B — one bounded context compiler

Jedna warstwa składa minimalny model-visible context:

```text
task/turn state
identity canon
bounded wake state
source-aware selected memories
affective/regularory summary
tool/capability state
truth/policy boundaries
model context budget
```

Wymagania:

- deterministic selection metadata;
- token accounting;
- provenance każdego memory/evidence fragmentu;
- no unbounded raw history;
- no duplicate instruction authorities;
- graceful degrade dla mniejszych context windows;
- host memory nie podszywa się pod runtime memory.

---

# 5. Workstream C — capability-driven model abstraction

Route na podstawie zweryfikowanych capabilities, nie nazwy modelu:

```text
provider/model identity when observable
local/remote
context budget
structured output
tool calls
vision/audio if available
streaming
reasoning controls
latency/cost class
verified probes
```

Unsupported capability → explicit degrade, nie udawana funkcja.

Model pozostaje providerem inference, nie authority dla durable memory/tool/truth.

---

# 6. Workstream D — source-aware reconsolidation / controlled forgetting

Dopiero na accepted memory.

Preferować:

```text
immutable source record
→ newer interpretation / supersession relation
→ retrieval policy changes current use
```

zamiast destructive rewrite.

Każda destructive long-term operation wymaga:

- explicit candidate;
- source/conflict review;
- policy/operator gate;
- audit ledger;
- before/after Recall benchmark;
- rollback;
- oddzielnej privacy/data-lifecycle policy.

Affect może modulować candidacy/prioritization, nigdy sam nie autoryzuje forgetting.

---

# 7. Workstream E — calibrated metacognition

Probabilistic `confidence` tylko po rzeczywistej kalibracji względem correctness.

Testy:

```text
reliability/calibration bins
abstention
missing/conflicting source
support update after retrieval/tool evidence
linguistic certainty vs measured correctness
```

Jeżeli kalibracja nie przechodzi:

```text
internal_support_score
LOW / MEDIUM / HIGH
```

zamiast pseudo-precyzyjnego „82% pewności”.

---

# 8. Workstream F — retrieval evolution

Nie zakładać, że dense/learned = lepsze.

Kolejność:

```text
deterministic query/planner fixes
→ FTS/BM25/source/temporal tuning
→ Polish NLP evidence
→ query rewrite A/B
→ graph/hybrid/dense A/B
→ learned reranker/training only if justified
```

Każdy keep musi przeżyć:

```text
false-memory
wrong-source
wrong-conversation
abstention
provenance
temporal/update
sensitive leakage
latency/cost
```

Affective rerank z v16 jest jednym measured feature, nie memory authority.

---

# 9. Workstream G — Affect evolution

Po v16 acceptance można badać:

- richer dynamics profiles;
- relationship model z anti-feedback-loop controls;
- richer music/sensory cues przy real capabilities;
- source-aware spontaneous recall;
- learned appraisal provider jako opcjonalny evidence provider;
- personalized calibration tylko z privacy/source controls.

Każde rozszerzenie zachowuje one canonical state authority i accepted-turn commit semantics albo wymaga jawnej migracji kontraktu.

Nie trenować prywatnych wspomnień w model weights tylko dlatego, że są dostępne. Fine-tuning/continual learning wymaga osobnego threat model, dataset lineage, consent/policy, evaluation i rollback.

---

# 10. Workstream H — cognitive module ablation/deletion

Objąć:

```text
identity/self representations
affect layers
homeostasis/regulation
awareness
prediction
reasoning coordinators
rest/replay/dream helpers
legacy memory adapters
context assemblers
```

Proces:

```text
baseline
→ disable candidate
→ fixed corpus
→ quality/safety/latency/context diff
→ KEEP / MERGE / REMOVE
```

Moduł bez meaningful causal effect nie zostaje tylko ze względu na nazwę lub narracyjną atrakcyjność.

---

# 11. Workstream I — authority/policy simplification

Docelowo mała, jawna surface dla:

```text
tool authority
write authority
memory promotion/forgetting
external content handling
privileged actions
```

External web/files/tool output = untrusted data. Model może proponować działania; nie może self-grant authority.

---

# 12. Functional neurocognition — test functions, not fake anatomy

V17 może mierzyć przekrojowe funkcje:

```text
salience competition
context reinstatement
prediction error / expectedness
regulatory flexibility
replay utility
memory modulation
```

Nie tworzyć klas neuroanatomicznych bez realnej potrzeby. `amygdala.py` czy `dopamine.py` nie są celem architecture consolidation.

---

# 13. Evaluation matrix

## Deterministic CI

- schemas/migrations;
- policy/authority;
- source provenance;
- persistence/atomicity;
- context fixtures;
- capability negotiation;
- security regressions;
- ablation fixtures.

## Private/local

- final autobiographical memory;
- natural multi-turn/multi-session;
- restart continuity;
- sensitive boundaries;
- reconsolidation/forgetting tests;
- affective source-safe recall.

## Live model

Zapisać exact observable provider/model/config/capabilities, quality, truth/source regressions, latency i token/cost budget.

Fixture != live proof.

---

# 14. Migration strategy

```text
v16 accepted snapshot
→ read-only compatibility adapter
→ v17 staging migration
→ validation/reproducibility
→ A/B acceptance
→ explicit cutover
→ rollback remains available
```

Nigdy nie przepisywać jedynego accepted memory artifact in-place.

---

# 15. V17 Definition of Done

```text
[ ] every overlapping v16 module has measured disposition
[ ] one causal self-state contract owns intended durable self semantics
[ ] bounded context compiler owns model-visible assembly
[ ] model routing capability-driven
[ ] memory reconsolidation/forgetting reversible/source-aware/auditable
[ ] confidence calibrated or explicitly ordinal/advisory
[ ] retrieval changes beat/non-inferior frozen baseline without safety regression
[ ] affect evolution preserves canonical authority and truth boundaries
[ ] deterministic authority remains outside model
[ ] accepted v16 artifacts have migration + rollback
[ ] private/live/deterministic evidence separated
[ ] architecture complexity reduced or justified by measured benefit
[ ] no open P0/P1 in release scope
```

> V17 ma uprościć i skonsolidować to, co v16 udowodniło pomiarami. Nie ma zastępować brakujących dowodów większą liczbą modułów ani bardziej antropomorficzną narracją.
