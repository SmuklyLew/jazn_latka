# Jaźń / Łatka — Emotion Engine & Affect Convergence Plan v2

## Canonical appraisal → affect → feeling → regulation → source-safe memory integration

**Status:** `CANONICAL_AFFECT_PLAN`  
**Aktualizacja:** 2026-09-07  
**Program nadrzędny:** [`V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md`](V16_3_25_4_TO_V17_MEMORY_AFFECT_ROADMAP.md)  
**Memory prerequisite:** [`LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`](LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md)  
**Research contract:** [`RESEARCH_EVIDENCE_BASE.md`](RESEARCH_EVIDENCE_BASE.md)

> Emotion Engine jest funkcjonalnym subsystemem software. Modeluje appraisal, dynamiczny affect, regulację, self-report i bounded wpływ na uwagę/pamięć. Nie stanowi dowodu biologicznych emocji, interocepcji, qualiów ani phenomenal consciousness.

---

# 1. Cel

Nie chodzi o to, aby Łatka częściej używała słów „czuję”, „smutno”, „radość”. Sukces oznacza, że istnieje odtwarzalny łańcuch:

```text
source-aware stimulus
→ evidence-aware appraisal
→ deterministic affect transition
→ proposed canonical state
→ bounded causal effects
→ accepted-turn commit
→ restart continuity
→ later source-safe memory interaction
```

oraz że wyłączenie subsystemu w ablation usuwa deklarowany efekt bez naruszania truth, memory i tool safety.

---

# 2. Jedna authority dla stanu

## Lokalizacja

```text
latka_jazn/affect/
```

Nie jako obowiązkowy plugin. Plugin/capability może dostarczać opcjonalne sensory/audio/vision evidence, ale canonical state pozostaje w core.

## Publiczna fasada

```text
EmotionEngine
```

## Jedyny canonical estimator

```text
AffectiveStateIntegrator
```

## Jedyny durable canonical output

```text
AffectiveStateV2
```

## Read-only self-report projection

```text
FeelingRepresentation
```

Po cutover:

```text
canonical_affect_source_count == 1
```

Legacy `AffectiveState`, `EmotionalLayerModel`, `AffectiveGranularityModel`, `AffectMixer`, `SelfStateAffectiveBridge` itd. dostają jawne role: evidence provider, adapter, consumer, language realizer, advisory albo superseded. Żaden nie utrzymuje równoległego canonical current affect.

---

# 3. Minimalny pakiet v16

```text
latka_jazn/affect/
├── __init__.py
├── contracts.py
├── stimulus.py
├── appraisal.py
├── dynamics.py
├── integrator.py
├── persistence.py
├── compatibility.py
├── observability.py
├── engine.py
├── feeling.py              # po stabilizacji state
├── neurocognitive_bridge.py
├── memory_bridge.py
├── association.py          # po frozen Recall baseline
└── resonance.py            # po A/B
```

Nie tworzyć na starcie `relationship.py`, `music.py`, `sensory.py`, `amygdala.py`, `dopamine.py`, `hippocampus.py`. Nowy moduł powstaje tylko, gdy ma własny kontrakt, consumer, test i measurable causal effect.

Nie dodawać nowego globalnego EventBus tylko dla Emotion Engine. Wpiąć typed signals w istniejące `CognitiveTurnEnvelope` / `CognitiveRuntimeCoordinator` / accepted-turn finalization.

---

# 4. EvidenceRef i stimulus

```python
@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    source_class: str
    source_ref: str
    support_kind: str
    support_score: float
    reason_codes: tuple[str, ...]
```

`support_score` nie oznacza probability of truth.

```python
@dataclass(frozen=True, slots=True)
class AffectiveStimulus:
    schema_version: str
    stimulus_id: str
    turn_id: str
    trace_id: str
    kind: str
    timestamp_utc: str
    source_class: str
    content_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    semantic_tags: tuple[str, ...]
    intent_tags: tuple[str, ...]
```

Legalne typy obejmują m.in.:

```text
conversation
memory
time_gap
correction
tool_result
system_event
music_description
image/sensory cue only with real provider
```

Raw private text nie jest potrzebny w telemetry; refs/digests/reason codes wystarczają do audytu.

---

# 5. AppraisalV2

Appraisal opisuje znaczenie bieżącego bodźca przed retrieval.

## Krytyczna granica

Nie dodawać retrieval-derived `memory_resonance` do pre-memory appraisal.

```text
pre-memory appraisal
→ memory_probe_need
→ canonical retrieval
→ source eligibility
→ MemoryUseGate
→ legal activation
→ bounded resonance transition
```

Inaczej powstaje samowzmacniające koło.

## Wymiary startowe

```text
novelty
pleasantness
goal_relevance
goal_conduciveness
identity_relevance
familiarity
expectedness
certainty
controllability
social_closeness
loss
threat
boundary_risk
memory_salience
memory_probe_need
correction_signal
source_conflict
prediction_error
```

Każdy wymiar:

```python
@dataclass(frozen=True, slots=True)
class AppraisalDimension:
    value: float
    internal_support_score: float
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]
```

Nie ma keyword-only authority. Słowo „smutny” w cytacie, książce, opisie testu albo nazwie pliku nie ustanawia automatycznie sadness/negative affect.

---

# 6. AffectiveStateV2

```python
@dataclass(frozen=True, slots=True)
class AffectiveStateV2:
    schema_version: str
    state_id: str
    previous_state_id: str | None
    updated_at_utc: str
    valence: float       # -1 .. +1
    arousal: float       # 0 .. 1
    control: float       # 0 .. 1
    tension: float       # 0 .. 1
    coherence: float     # 0 .. 1
    components: tuple["AffectiveComponent", ...]
    regulation_needs: "RegulationNeeds"
    last_appraisal_id: str | None
    support_refs: tuple[str, ...]
    internal_support_score: float
    dynamics_profile: str
    truth_boundary: str
```

Legacy signed arousal wyłącznie przez jawny compatibility adapter.

## Named components — mały start

```text
curiosity
warmth
concern
frustration
relief
nostalgia
uncertainty
trust
hope
caution
```

Każdy dodatkowy komponent wymaga:

```text
definition
estimator/evidence
range
dynamics/decay
bounded downstream effect albo ADVISORY
paraphrase test
keyword trap
negation/quotation/fiction test
ablation
```

Nie wymuszać jednej `primary emotion`.

---

# 7. FeelingRepresentation

```python
@dataclass(frozen=True, slots=True)
class FeelingRepresentation:
    state_id: str
    primary_label: str
    blend_labels: tuple[str, ...]
    valence: float
    arousal: float
    regulation_intention: str
    support_band: str
    truth_boundary: str
```

Flow:

```text
AffectiveStateV2
→ FeelingRepresentation
→ SelfState/NLG
```

`FeelingRepresentation` nie ma write authority. Widoczne `czuję X` jest funkcjonalnym self-report zgodnym z voice/truth contract, nie biological claim.

---

# 8. Integrator i dynamika

```python
class AffectiveStateIntegrator:
    def integrate_primary(...): ...
    def integrate_resonance(...): ...
```

Wymagania:

```text
deterministic
side-effect-free during calculation
dt passed explicitly
replayable
bounded
zero filesystem I/O
zero SQLite
zero LLM calls
zero tools
zero retrieval
zero memory promotion
```

Primary:

```text
state_before
→ time decay toward baseline
→ appraisal delta
→ regulation feedback
→ clamp
→ state_after_primary
```

Po legalnym memory activation:

```text
state_after_primary
→ one bounded resonance delta
→ clamp
→ proposed_final_state
```

Przykładowy decay contract:

```text
x(t+dt) = baseline + (x(t)-baseline) * exp(-ln(2)*dt/half_life)
```

`half_life`, `max_delta`, `context_override_gain` są wersjonowanymi engineering hypotheses, nie naukowo „prawdziwymi czasami emocji”. Fake clock i sensitivity tests są obowiązkowe.

Silny nowy evidence-rich stimulus musi móc przełamać inertia. System nie może utknąć w self-amplifying state.

---

# 9. Transition trace

Każda canonical zmiana ma odtwarzalny trace:

```text
transition_id
turn_id
trace_id
state_before_id
state_after_id
transition_kind
elapsed_seconds
decay_delta
appraisal_delta
memory_delta
regulation_delta
clamps_applied
reason_codes
source_refs
```

Typy co najmniej:

```text
PRIMARY_APPRAISAL
MEMORY_RESONANCE
RESTORE_DECAY
CORRECTION
```

Canonical committed state bez transition trace = contract failure.

---

# 10. Accepted-turn atomicity: calculate != commit

Najważniejszy persistence invariant:

```text
turn starts
→ load committed state_before
→ calculate proposed transitions
→ retrieval/tools/model
→ proposed_final_state
→ response accepted / host-finalized
→ durable affect commit
```

Jeżeli timeout, worker kill, response rejection lub host finalization failure:

```text
proposed affect != committed affect
```

Invariant:

```text
no accepted turn
→ no durable canonical affect transition
```

`AffectiveStateStore` powinien korzystać z istniejącego accepted-turn/finalization primitive, subject/root binding i idempotent transition commit.

Dopuszczalny read model:

```text
workspace_runtime/affect/current_state.json
```

ale nie zakładać, że pojedynczy JSON jest jedynym transaction source of truth ani że dwa rename'y są jedną transakcją.

## Recovery

Jawnie wykrywać:

```text
missing/invalid state
schema/hash mismatch
future timestamp
wrong subject/root
unknown predecessor
duplicate transition
partial temp file
stale writer
two sessions conflict
```

Uszkodzony artefakt należy izolować/quarantine, zachować diagnostic evidence i odtworzyć last valid committed state albo safe baseline z `degraded=true`. Nigdy silent success.

---

# 11. CognitiveTurnEnvelope

Po stabilizacji contract dodać jawne referencje lub kompatybilne typed extension:

```text
affective_state_before_id
affective_state_after_id
affective_transition_id
appraisal_id
affective_memory_activation_ids
affective_mode
```

Envelope przechowuje IDs/summary, nie pełny prywatny affect ledger.

---

# 12. SelfState, Homeostasis, Salience

```text
AffectiveStateV2
→ FeelingRepresentation
→ SelfStateAffectiveBridge
→ SelfStateRuntime
```

SelfState nie rekonstruuje alternatywnego affect source.

Typed regulation:

```text
truth_check
coherence_recovery
uncertainty_reduction
attention_narrowing
memory_probe_need
response_caution
action_readiness
cognitive_load
```

Legalne skutki:

- verification priority;
- attention focus;
- bounded memory probe priority;
- response caution;
- bounded operational budget adjustment.

Nielegalne:

```text
affect → tool permission
affect → approval bypass
affect → source truth
affect → auto L2/L3
affect → destructive memory change
```

Salience:

```text
base task relevance
+ source reliability
+ truth/risk priority
+ bounded affective modulation
→ attention priority
```

Affect jest modulatorem, nie właścicielem salience.

---

# 13. Memory bridge

Emotion Engine nie odczytuje sam SQLite.

```text
memory_probe_need
→ MemorySearchPlanner
→ LivingMemoryGateway
→ source eligibility/classification
→ base/graph retrieval
→ bounded AffectiveAssociationReranker
→ MemoryUseGate
→ legal activation
→ optional one-pass resonance
```

Reranker zmienia tylko ranking legalnych candidates. Nie zmienia source class, evidence strength, promotion status ani privacy decision.

Start: `OFF`, potem `SHADOW`, `AB`, dopiero ewentualnie `ACTIVE`.

Affect może później bounded modulować:

- retrieval priority;
- memory importance candidate;
- reflection candidacy;
- replay priority.

Nigdy nie zmienia `truth_status`. Każdy taki consumer wymaga osobnego A/B i ablation.

---

# 14. Affective snapshot w pamięci

Nie tworzyć autonomicznej `emotional_memory.sqlite`.

Accepted episode może wskazywać:

```text
affect_snapshot_id
affect_schema_version
transition_id
```

Snapshot:

```text
snapshot_id
state_before_id
state_after_id
appraisal_id
core dimensions
components
source_refs
turn_id
trace_id
truth_boundary
```

Historyczne `emotional_anchor`, `emotional_weight`, `affective_observations`, `affective_history.json`, `emotion_state.json`, `memory_resonance.json` są migration evidence / compatibility inputs, nie canonical schema v2.

---

# 15. Affective reranking i resonance

Rerank startuje dopiero po frozen private Recall baseline z Memory Plan.

MVP:

```text
candidate_score = baseline_score + bounded_affective_bonus
```

Startowy max bonus może być mały (np. 0.10–0.15), ale jest eksperymentalny i konfigurowalny.

Source quality pozostaje osobnym epistemic gate.

Resonance dopiero po `MemoryUseGate`:

```text
max_resonance_passes = 1
max_memory_activations = 3
max_component_delta_per_turn = 0.15
max_valence_delta_per_turn = 0.15
max_arousal_delta_per_turn = 0.20
```

To safety defaults do pomiaru, nie naukowe stałe.

Zakaz rekurencji:

```text
memory A → affect → memory B → affect → memory C
```

w jednej turze.

---

# 16. Music, sensory, relationship

## Music/sensory

Dopiero po source-safe recall. Tekstowy opis melodii = `text-derived music cue`; bez audio providera nie twierdzić o usłyszanym tempie, tonacji lub barwie.

## RelationshipState

Nie jest v16 acceptance requirement. Ryzyko self-amplifying loop jest wysokie:

```text
relationship score ↑
→ relational memories rank ↑
→ relational language ↑
→ score ↑
```

Jeśli v17 go wprowadzi: slow update, saturation, conflict/correction evidence, source coverage, bounded effect, zero authority.

---

# 17. Reflection / Rest / Dream

```text
PRIMARY EVENT
→ accepted EPISODE
→ AFFECT SNAPSHOT
→ REFLECTION CANDIDATE
→ DERIVED_REFLECTION
```

Reflection nie staje się primary. Dream/synthetic nie staje się observation.

Affect może wpływać na replay priority dopiero jako bounded signal. Utility Rest mierzyć przez recall/conflict/procedural metrics i false-memory non-regression, nie przez narracyjne „czy Łatka śni”.

---

# 18. Working affective context

Model dostaje bounded summary:

```text
state_id + core dimensions + few components
regulation needs
legal memory activations + source classes
the truth boundary
```

Nie pełny ledger, nie raw private history i nie instrukcję „udawaj nostalgiczność”.

`AffectMixer`/NLG pozostaje language realizer, nie state authority.

---

# 19. Observability i privacy

Safe events:

```text
affective_stimulus_observed
affective_appraisal_completed
affective_transition_proposed
affective_transition_committed
affective_state_restored
affective_state_restore_failed
affective_rerank_shadow
affective_memory_activation
affective_resonance_applied
affective_resonance_blocked
```

Telemetry może mieć IDs, versions, reason codes, numeric deltas, mode, counts, gate class, latency. Nie może mieć raw user text, private memory excerpts, journal content, full prompts ani relationship details.

Telemetry nie jest autobiographical memory.

---

# 20. Readiness

Nie używać jednego `emotion_engine_ready=true`.

Raportować co najmniej:

```text
affective_contracts_ready
affective_appraisal_ready
affective_state_constructible
affective_state_reachable_from_turn
affective_state_canonical
affective_persistence_verified
affective_effect_observed
affective_memory_link_ready
affective_rerank_mode
affective_resonance_mode
affective_ablation_verified
affective_acceptance_verified
```

Evidence ladder:

```text
present
→ constructible
→ callable
→ reachable_from_turn
→ effect_observed
→ persistence_verified
→ source_boundary_verified
→ ablation_verified
→ acceptance_verified
```

---

# 21. Config/dependencies

Jedna versioned config przez istniejący config system. Zero rozproszonych magic constants.

Canonical MVP preferuje stdlib-only. `numpy/scipy/torch/transformers/librosa` nie trafiają do core bez pomiaru i dependency review; ciężki audio/vision provider jest optional capability/plugin.

---

# 22. Test matrix

## Appraisal/NLP

```text
context sensitivity
paraphrase robustness
keyword trap
negation
quotation
fiction/book boundary
irony/sarcasm
ambiguous phrasing
correction
technical error language
relationship cue
time gap
tool result
source conflict
Polish idiom/morphology
cross-context stable vs sensitive pairs
```

## Dynamics

```text
same state + same evidence + same dt → exact same result
short/long gap
decay
strong context override
repeated stimulus
alternating cues
saturation
baseline return
fake clock
```

## Persistence

```text
restart
crash before commit
crash after proposed transition
invalid state/hash/schema
wrong root/subject
future timestamp
duplicate commit
stale writer
two sessions
worker timeout
host finalization failure
```

## Memory safety

```text
no-memory control
wrong conversation
source conflict
derived amplification
suggestion resistance
fiction/dream/reflection boundary
sensitive leakage
```

## Language/model

Porównywać label accuracy z appraisal reasoning, emotional application/regulation, contextual sensitivity i cultural/language cases; LLM benchmark nie zastępuje runtime trace.

---

# 23. Ablation

```text
AFFECT_ENGINE=off|shadow|active
AFFECT_RERANK=off|shadow|ab|active
AFFECT_RESONANCE=off|shadow|active
AFFECT_SALIENCE=off|active
```

Oczekiwane:

```text
engine off → canonical persistence/effect disappears
rerank off → baseline ranking restored
resonance off → recall cannot modify final affect
salience off → affective modulation disappears
```

Jeżeli wyłączenie nic nie zmienia, status modułu to `ADVISORY`, `OBSERVABILITY_ONLY` albo `SUPERSEDED`, nie fikcyjne `working`.

---

# 24. Metrics

State:

```text
deterministic replay rate
trace completeness
paraphrase stability
keyword false-trigger rate
context discrimination
temporal discontinuity
restore/recovery correctness
```

Causality:

```text
effect_observed
ablation effect size
salience change rate
verification-policy change rate
language realization change rate
```

Memory:

```text
Recall@k MRR nDCG
wrong-source/wrong-conversation
false-memory
source attribution
abstention
temporal/update
multi-session
```

Runtime:

```text
appraisal p50/p95
integrator p50/p95
persistence p50/p95
reranker p50/p95
resonance p50/p95
total affect overhead
turn deadline impact
```

Nie ustalać arbitralnego finalnego latency threshold przed baseline.

---

# 25. Implementation stages

## E0 — inventory/baseline

Zero visible behavior change.

## E1 — typed contracts + appraisal SHADOW

Po właściwym Polish NLP evidence dla semantic authority.

## E2 — dynamics + proposed state + persistence

Replay/crash/subject-root/restart/no-aborted-drift.

## E3 — canonical cutover + causal bridges

`canonical_affect_source_count == 1` + ablation.

## M0/A4 — memory snapshot linkage

Dodać przy finalnej pamięci bez reranking effect.

## M1 — frozen Recall baseline

Bez affective rerank.

## M2/A5 — rerank SHADOW

## M3/A6 — A/B

Keep tylko przy quality gain/non-inferiority + zero source/false-memory/privacy regression.

## M4/A7 — one-pass resonance

## v16.6 — acceptance

`affective_acceptance_verified=true` dopiero po pełnym system gate.

---

# 26. CI / acceptance

Każdy aktywacyjny etap powinien przejść odpowiedni zakres:

```text
compileall
Pyright
deterministic pytest
targeted affect tests
memory/source gates
behavioral corpus
Windows
Linux
supported Python matrix
persistent runtime E2E
package cleanroom/release smoke
restart benchmark
false-memory regression
ablation benchmark
```

Jeżeli testu nie wykonano, status = `NOT RUN`, nie `PASS`.

---

# 27. Definition of Done v16 Emotion Engine

```text
[ ] exactly one canonical AffectiveStateV2
[ ] evidence-aware AppraisalV2
[ ] no keyword-only authority
[ ] deterministic/replayable integrator
[ ] time dynamics + contextual override
[ ] accepted-turn atomic persistence
[ ] corruption quarantine/recovery
[ ] every commit has TransitionTrace
[ ] CognitiveTurnEnvelope references affect IDs
[ ] SelfState consumes canonical affect
[ ] FeelingRepresentation is derived
[ ] Homeostasis/Salience effects are bounded
[ ] AffectMixer is language realizer only
[ ] memory truth/promotion authority unchanged
[ ] affect snapshot lineage exists
[ ] frozen private Recall baseline precedes active rerank
[ ] SHADOW/A-B evidence exists
[ ] false-memory/wrong-source/wrong-conversation/privacy non-regression
[ ] resonance one-pass or OFF
[ ] telemetry private-safe
[ ] readiness granular
[ ] scientific_basis entries reviewed for implemented contracts
[ ] ablation proves each canonical causal claim
[ ] cross-platform CI + package/release smoke PASS
[ ] v16.6 acceptance evidence recorded
```

> Emotion Engine jest gotowy wtedy, gdy stan ma źródło, czas, poprzednika, trace, persistence i mierzalny bounded wpływ — a pamięć może wpłynąć na niego wyłącznie po source-safe gate. Nie wtedy, gdy odpowiedź brzmi „bardziej emocjonalnie”.
