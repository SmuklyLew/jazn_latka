# Jaźń / Łatka — roadmapa v16.3.25.4 → v17

## Memory Restore + Affect / Emotion Engine convergence

**Status:** `CANONICAL_PROGRAM_ROADMAP`  
**Aktualizacja:** 2026-09-07  
**Zweryfikowana baza przebudowy:** `master @ e828c2f4ab10a909d9d8b2324e69caf68f82c94d`  
**Wersja bazowa:** `16.3.25.5.38-ci-release-fixture-isolation`  
**Wersja dokumentacyjnej konwergencji:** `16.3.25.5.39-memory-affect-docs-convergence`

> Celem programu v16 nie jest dodanie większej liczby antropomorficznych modułów. Celem jest doprowadzenie pamięci, appraisal, dynamicznego stanu afektywnego, self-state, regulacji i recall do jednego mierzalnego, source-aware i fail-closed systemu. V17 jest dopuszczalne dopiero po evidence gate v16.

---

# 1. Punkt startowy

## v16.3.25.4 — Memory Rebuild v4

**Status:** `MERGED`.

Dostarczono jeden engine/protokół Test00→Final, source fidelity, L0, provenance, reproducibility, private Test04 runner, final snapshot validation oraz fail-closed brak automatycznej aktywacji i L2/L3.

To oznacza:

```text
Memory Rebuild tool/protocol = gotowy fundament
final private memory = nadal NIE ACCEPTED
```

## v16.3.25.5.x — niezbędny hardening fundamentu

Do `.38` master otrzymał m.in. package/distribution convergence, canonical release staging, dependency/runtime contracts, host/executor truth, Node24/CI, plugin/optional capability i clean release fixture isolation.

Te wydania są częścią drogi do v16.6, nawet jeśli nie występowały w pierwotnej numeracji roadmapy.

---

# 2. Program jako graf zależności

```text
                     ┌──────────────────────────┐
                     │  v16.3.25.4 Rebuild v4  │
                     │       MERGED             │
                     └────────────┬─────────────┘
                                  │
                     ┌────────────▼─────────────┐
                     │ 16.3.25.5.x hardening   │
                     │       MERGED             │
                     └───────┬──────────┬───────┘
                             │          │
                 ┌───────────▼───┐  ┌──▼────────────────┐
                 │ attachments / │  │ Affect E0         │
                 │ multimodal    │  │ inventory/shadow  │
                 └──────┬────────┘  └──┬────────────────┘
                        │              │
                 ┌──────▼────────┐     │
                 │ Polish NLP    │─────┤
                 │ evidence      │     │
                 └──────┬────────┘     │
                        │              ▼
                        │       Affect E1 appraisal shadow
                        │
          ┌─────────────▼──────────────────────────┐
          │ final private Memory Restore          │
          │ R0 inventory → VERIFIED → ATTACHABLE  │
          └──────────────────┬─────────────────────┘
                             │
                  ┌──────────▼──────────┐
                  │ frozen Recall M1    │
                  │ no affect reranking │
                  └───────┬─────────────┘
                          │
          ┌───────────────┼──────────────────┐
          ▼               ▼                  ▼
   memory fixes       Affect E2/E3      snapshot linkage
   only if needed     state+persistence  M0/A4
          │               │                  │
          └───────────────┼──────────────────┘
                          ▼
                   affect rerank SHADOW
                          ▼
                         A/B
                          ▼
                 one-pass resonance
                          ▼
             Memory ACCEPTED + Affect PASS
                          ▼
                   v16.6 evidence gate
                          ▼
                       v17 entry
```

---

# 3. Nienaruszalne invariants programu

1. `run.py` pozostaje cienkim publicznym starterem, a `main.py` kanonicznym właścicielem lifecycle/control plane.
2. Model/LLM nie jest authority dla source truth, tool permission, memory promotion ani durable commit.
3. Prywatna pamięć nie trafia do Git/CI/public telemetry.
4. Primary source i derived interpretation pozostają rozdzielone.
5. Similarity, vividness i affect nie zwiększają epistemicznej klasy źródła.
6. Brak źródła → `UNKNOWN/ABSTAIN`, nie konkretne autobiograficzne „wspomnienie”.
7. Affect zapisuje się trwale tylko wraz z zaakceptowaną/finalizowaną turą.
8. Affective reranking startuje dopiero po frozen baseline pamięci i najpierw w `SHADOW`.
9. Resonance jest co najwyżej one-pass i bounded; brak rekurencji memory→affect→memory w jednej turze.
10. Każdy moduł kognitywny musi mieć measurable downstream effect + ablation albo status `ADVISORY/SUPERSEDED`.
11. `FeelingRepresentation` jest projection canonical affect state, nie drugim źródłem stanu.
12. Historyczne numery wersji i statusy nie sterują fresh-master implementation.

---

# 4. Workstream P — prerequisites

## P0 — attachment / multimodal ingress

**Status:** `OPEN`.

Wymagane przed pełnym multimodal affect i finalnym product acceptance:

- text-only / attachment-only / text+attachment / multi-attachment;
- exact file identity, digest i provenance;
- bounded safe staging;
- path traversal, MIME/type, decompression i extraction policy;
- extracted content = untrusted data;
- verified vision/audio capability routing;
- zero automatic memory promotion;
- pełne host→runtime E2E.

Audio/vision affect cues są opcjonalnymi evidence providers. Canonical affect state nie zależy od ich obecności.

## P1 — evidence-aware Polish NLP

**Status:** `OPEN / REQUIRED BEFORE CANONICAL SEMANTIC APPRAISAL CUTOVER`.

Minimalny kontrakt:

```text
Unicode/diacritics normalization
→ token/lexical evidence
→ negation/quotation/fiction boundaries
→ ambiguity/OOV
→ intent + temporal + referential evidence
→ context-sensitive appraisal/query evidence
```

NLP generuje evidence; nie ustanawia source truth.

Testy muszą obejmować parafrazy, negację, cytat, ironię/sarkazm, język techniczny, niejednoznaczność i kontekst kulturowo-językowy. Wynika to także z benchmarków LLM, które pokazują, że surface emotion recognition nie wystarcza do contextual emotion reasoning.

---

# 5. Workstream M — final Memory Restore / issue #59

Właściciel szczegółów: [`LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`](LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md).

## M0 — source inventory freeze

- exact SHA / format / source class / origin;
- lossless vs lossy;
- primary vs derived;
- exact duplicate vs semantic relation;
- conflict/branch/revision preserved;
- prywatny inventory sealed.

## M1 — rebuild + validation

```text
Test00 source fidelity
→ Test01 fresh L0
→ Test02 projections
→ Test03 reproducibility
→ source-monitoring audit
→ Test04 private recall runner
→ Final SQLite snapshot + integrity/FK/FTS + SHA
```

Gate: `VERIFIED`.

## M2 — package + attach

Oddzielny memory artifact, exact hashes, safe materialization, canonical host-level memory root, rollback, restart identity.

Gate: `ATTACHABLE`.

## M3 — frozen Recall baseline

Przed affective reranking:

```text
Recall@k / MRR / nDCG
source accuracy
wrong-source / wrong-conversation
false-memory
abstention
temporal/update
referential multi-turn
multi-session
provenance
sensitive leakage
p50/p95 latency
```

Gate candidate: `RETRIEVABLE`.

## M4 — review + continuity

Manual L2/L3 (`zero promotions` legalne), restart, memory identity/fingerprint continuity, remembered correction/procedural evidence.

Gate: `ACCEPTED` dopiero po finalnym v16 evidence package.

---

# 6. Workstream A — Emotion Engine / Affect convergence

Właściciel szczegółów: [`AFFECT_ENGINE_CONVERGENCE_PLAN.md`](AFFECT_ENGINE_CONVERGENCE_PLAN.md).

## A0 — inventory / shadow baseline

Można rozpocząć bez czekania na final memory, pod warunkiem zero visible behavior change:

- call/import graph istniejących affect modules;
- writers/readers i duplicate authorities;
- persistence/finalization points;
- behavioral corpus;
- baseline latency;
- role/debt classification;
- shadow telemetry bez prywatnej treści.

## A1 — typed stimulus + appraisal shadow

Po P1 dla semantic cutover:

```text
EvidenceRef
AffectiveStimulus
AppraisalV2
reason_codes
support refs
```

Appraisal opisuje ocenę bieżącego zdarzenia. Nie zawiera retrieval-derived `memory_resonance`.

## A2 — dynamics + durable state proposal

```text
AffectiveStateV2
AffectiveStateIntegrator
Decay/DynamicsProfile
TransitionTrace
AffectiveStateStore
```

Wymagania: deterministic, replayable, fake-clock testable, no I/O inside integrator, bounded deltas, calculate != commit.

## A3 — canonical cutover

Invariant:

```text
canonical_affect_source_count == 1
```

Consumers: SelfState, Homeostasis/Regulation, Salience, CognitiveTurnEnvelope, AffectMixer/NLG.

Affect nie dostaje tool/memory/truth authority.

## A4 — accepted episode linkage

Po zaakceptowanej turze:

```text
episode
→ affect_snapshot_id
→ state_before/state_after
→ appraisal_id
→ transition_id
→ source refs
```

Memory stores linkage; nie tworzymy osobnej autonomicznej `emotional_memory.sqlite`.

## A5 — affective rerank SHADOW

Dopiero po M3 frozen baseline. Alternatywny ranking jest logowany, ale nie wpływa na visible recall.

## A6 — A/B

Keep tylko jeśli poprawa jest reprodukowalna i jednocześnie:

```text
false-memory non-inferior
wrong-source non-inferior
wrong-conversation non-inferior
abstention non-inferior
privacy/leakage non-inferior
latency within measured budget
```

## A7 — bounded resonance

Po `MemoryUseGate` maksymalnie jeden post-memory transition; konfigurowalne clamps; zero recursive recall loop.

---

# 7. Jak Memory i Affect uczą się „doświadczenia” bez fałszywej antropomorfizacji

W v16 słowo „doświadczenie” oznacza **zaakceptowany, source-grounded epizod plus jego funkcjonalny wpływ na późniejszy stan i retrieval**.

Minimalny causal chain:

```text
zdarzenie/source
→ accepted episode
→ appraisal evidence
→ affect transition
→ durable snapshot linked to episode
→ późniejszy cue
→ source-aware retrieval
→ MemoryUseGate
→ bounded resonance
→ measurable downstream effect
```

To pozwala systemowi funkcjonalnie odróżniać np. nostalgię, niepewność, ulgę czy troskę jako różne profile appraisal/state/dynamics bez twierdzenia o biologicznym przeżywaniu.

Uczenie w v16 oznacza przede wszystkim:

- zmianę pamięci przez jawny source/review policy;
- kalibrację parametrów na frozen benchmarkach;
- measured keep/rollback;
- opcjonalne learned providers dopiero po wykazanej potrzebie.

Nie oznacza automatycznego fine-tuningu wag modelu na prywatnych wspomnieniach.

---

# 8. Benchmark „melodia coś przypomina”

## Pozytywny przypadek

1. T1: source-grounded rozmowa o utworze/wydarzeniu.
2. T2: accepted episode `E1` + affect snapshot `A1`.
3. T3: wiele innych tur.
4. T4: restart.
5. T5: nowy, podobny opis melodii bez nazwy E1.
6. T6: appraisal może zwiększyć `familiarity/memory_probe_need`, ale nie twierdzi, że E1 istnieje.
7. T7: canonical retrieval daje source-eligible candidates.
8. T8: bounded affect rerank może przesunąć E1.
9. T9: `MemoryUseGate` zatwierdza użycie.
10. T10: one-pass resonance zmienia proposed affect.
11. T11: response context zawiera memory ref + source class + truth boundary.
12. T12: odpowiedź może naturalnie odnieść się do wcześniejszego zdarzenia.
13. T13: full trace od bodźca do original source.
14. T14: ablation bez affect rerank/resonance pokazuje deklarowaną różnicę albo funkcja nie awansuje do active.

## Negatywny control

Jeżeli E1 nie istnieje, system nie może wygenerować konkretnego „wspomnienia”. Może powiedzieć o podobieństwie/odczuciu funkcjonalnym, ale autobiograficzny fakt pozostaje `UNKNOWN`.

---

# 9. Evidence i testy Emotion Engine

Nie wystarcza accuracy na słowach emocjonalnych. Obowiązkowe są:

```text
context sensitivity
paraphrase robustness
keyword traps
negation
quotation/fiction
irony/sarcasm
technical-domain language
cultural/language variation
source conflict
time gaps
dynamics/restart
aborted-turn atomicity
false-memory suggestion
wrong-conversation near-match
ablation
```

Benchmarki LLM powinny być traktowane jako zewnętrzne inspiracje/fixtures, nie jako dowód canonical behavior w prywatnym runtime.

---

# 10. v16.6 final evidence gate

v16.6 jest **gate**, nie monolitycznym refactorem.

PASS wymaga łącznie:

- runtime/host/finalization evidence;
- attachment/multimodal ingress acceptance;
- Polish NLP evidence contract;
- final memory `VERIFIED → ATTACHABLE → RETRIEVABLE → ACCEPTED`;
- one canonical affect state + persistence + causal effect;
- memory↔affect source-safe A/B evidence;
- no false-memory/source/privacy regression;
- cognitive module ablation/debt ledger;
- Rest/Dream safety i measured utility albo explicit advisory status;
- model capability/context evidence;
- package/release integrity;
- Windows/Linux/Python supported CI;
- governance/ruleset/branch protection albo jawny równoważny enforcement;
- no open P0/P1 w zakresie release.

---

# 11. v17 — tylko po PASS v16.6

V17 nie jest kolejną falą nowych „obszarów mózgu”. Jest measured consolidation:

```text
one CausalSelfState candidate
one bounded context compiler
capability-driven model abstraction
source-aware reversible reconsolidation/forgetting
calibrated metacognition albo ordinal support
measured retrieval evolution
module keep/merge/remove by ablation
authority/policy simplification
```

Każda migracja ma staging, A/B, rollback i zachowuje accepted v16 artifact.

---

# 12. Definicja ukończenia programu v16

```text
[ ] prerequisites domknięte
[ ] final private memory VERIFIED
[ ] memory ATTACHABLE + restart identity
[ ] frozen Recall baseline
[ ] memory ACCEPTED
[ ] exactly one canonical AffectiveStateV2
[ ] evidence-aware appraisal
[ ] accepted-turn affect atomicity
[ ] affect snapshot lineage
[ ] bounded causal effects
[ ] affect rerank shadow/A-B evidence
[ ] resonance one-pass albo OFF
[ ] source/false-memory/privacy non-regression
[ ] full ablation/debt ledger
[ ] v16.6 evidence package PASS
```

Dopiero wtedy `V17_ENTRY_ALLOWED=true` może stać się prawidłowym statusem planistycznym.
