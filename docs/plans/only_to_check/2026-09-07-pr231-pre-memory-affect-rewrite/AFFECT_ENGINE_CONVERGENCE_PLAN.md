# Jaźń / Łatka — Emotion Engine & Affect Convergence Plan v1.0

## Kanoniczny plan konwergencji appraisal, affect, feeling, pamięci emocjonalnej, self-state i regulacji

**Status:** `CANONICAL_SUBPLAN`  
**Aktualizacja:** 2026-09-07  
**Zweryfikowana baza repo:** `master @ 378e9e6aceb83edbd679751e19cbe5c64c978025`  
**Bieżąca wersja bazowa:** `16.3.25.5.36-ci-archive-scope-contract-hardening`  
**Nadrzędny przebieg programu:** [`PLAN_EXECUTION_HISTORY.md`](PLAN_EXECUTION_HISTORY.md)  
**Bieżący krok:** [`CURRENT_STEP.md`](CURRENT_STEP.md)  
**Memory prerequisite:** [`LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md`](LATKA_MEMORY_RESTORE_AND_REBUILD_PLAN.md)

> Emotion Engine modeluje dynamiczny, trwały **software state** wykorzystywany w appraisal, regulacji, uwadze, pamięci i self-report. Nie implikuje biologicznych emocji, hormonów, interocepcji, bólu, cielesnego przeżywania ani phenomenal consciousness.

---

# 1. Decyzja architektoniczna

## Lokalizacja

Docelowy subsystem:

```text
latka_jazn/affect/
```

Nie:

```text
latka_jazn/plugins/EmotionEngine/
latka_jazn/modules/
latka_jazn/EmotionEngine/
```

Powód: affect jest częścią core cognition/runtime state. Nie może być opcjonalnym pluginem, od którego zależy istnienie głównego self-state.

### Pluginy są legalne tylko jako dodatkowe providery

Przykładowo później:

```text
optional audio feature provider
optional vision affect cue provider
optional external embedding provider
```

ale **canonical affect state i jego persistence pozostają w core**.

## Publiczna fasada

```text
EmotionEngine
```

## Jedyny kanoniczny estimator aktualnego stanu

```text
AffectiveStateIntegrator
```

## Jedyny kanoniczny durable output

```text
AffectiveStateV2
```

## Self-report

```text
FeelingRepresentation
```

jest pochodną read-only projection z canonical state, a nie drugim źródłem emocjonalnej prawdy.

---

# 2. Problem, który rozwiązujemy

Aktualny system posiada kilka częściowo nakładających się warstw:

```text
core/emotions.py::AffectiveState
core/emotion_layers.py::EmotionalLayerModel / AppraisalVector
core/affective_granularity.py::AffectiveGranularityModel
AffectMixer
SelfStateAffectiveBridge
SelfStateRuntime
HomeostasisRegulator
NeurocognitiveLoop
cognitive salience / state graph / turn envelope
```

Obecny problem:

```text
wiele estimatorów
+ różne skale
+ częściowo różne semantyki
+ keyword dependence
+ brak jednego durable transition contract
+ brak jednej accepted-turn commit semantics
```

Celem nie jest dodanie jeszcze jednego modelu. Celem jest **konwergencja**.

---

# 3. Nadrzędna zasada

Nie mierzyć sukcesu tym, czy Łatka częściej mówi:

```text
„czuję...”
„jest mi...”
„ta melodia mnie wzrusza...”
```

Mierzyć:

```text
czy istnieje stan przed bodźcem
czy appraisal ma evidence
czy przejście jest deterministyczne i audytowalne
czy stan ma poprzednika i czas
czy commit następuje tylko dla accepted turn
czy stan przetrwa restart
czy ma bounded downstream effect
czy pamięć może wpłynąć na stan tylko source-safe
czy ablation usuwa deklarowany efekt
czy false-memory nie rośnie
```

---

# 4. Docelowy pipeline

```text
USER / TOOL / ENVIRONMENT EVENT
              │
              ▼
      NLP + SOURCE EVIDENCE
              │
              ▼
       AffectiveStimulus
              │
              ▼
        AppraisalV2
              │
              ▼
    previous committed state
              │
              ▼
   AffectiveStateIntegrator
       PRIMARY TRANSITION
              │
              ▼
     proposed primary state
              │
       ┌──────┴────────┐
       ▼               ▼
 regulation        memory_probe_need
       │               │
       │               ▼
       │       MemorySearchPlanner
       │               │
       │               ▼
       │       LivingMemoryGateway
       │               │
       │               ▼
       │        source eligibility
       │               │
       │               ▼
       │        graph/base retrieval
       │               │
       │               ▼
       │    affective rerank (bounded)
       │               │
       │               ▼
       │         MemoryUseGate
       │               │
       │               ▼
       │      legal memory activation
       │               │
       │               ▼
       │        one-pass resonance
       └───────┬───────┘
               ▼
       proposed final state
               │
       ┌───────┼───────────┐
       ▼       ▼           ▼
   SelfState Homeostasis Salience
       │       │           │
       └───────┼───────────┘
               ▼
      FeelingRepresentation
               │
               ▼
     CognitiveTurnEnvelope
               │
               ▼
        AffectMixer / NLG
               │
               ▼
            LLM/model
               │
               ▼
        proposed response
               │
               ▼
      TURN ACCEPT / FINALIZE
               │
       ┌───────┼──────────────┐
       ▼       ▼              ▼
 final reply  affect commit  accepted episode
                          │
                          ▼
                  affect_snapshot_id
```

---

# 5. Scientific/engineering boundary

Plan czerpie **funkcjonalne inspiracje** z:

- appraisal / Component Process Model;
- dimensional affect / circumplex;
- computational appraisal (np. EMA/FAtiMA jako wzorce modularności);
- source monitoring;
- autobiographical memory;
- affective dynamics/inertia;
- emotion regulation;
- music-evoked/involuntary autobiographical cues;
- agent memory/retrieval/ablation.

Nie implementować klas typu:

```text
amygdala.py
hippocampus.py
dopamine.py
prefrontal_cortex.py
```

bez realnego, mierzalnego kontraktu. Zamiast nazw biologicznych budować funkcje:

```text
salience competition
prediction error / expectedness
context reinstatement
memory encoding modulation
regulatory flexibility
bounded replay/consolidation
```

---

# 6. Minimalna struktura pakietu

## MVP

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
└── engine.py
```

## Po canonical state

```text
├── feeling.py
├── neurocognitive_bridge.py
├── memory_bridge.py
├── association.py
└── resonance.py
```

## Nie tworzyć na starcie

```text
relationship.py
music.py
sensory.py
prediction_error.py
```

jeśli nie ma jeszcze consumer, testu i mierzalnego causal effect.

---

# 7. Klasyfikacja istniejących warstw

| Istniejący komponent | Rola docelowa |
|---|---|
| `AffectiveState` | `COMPATIBILITY_INPUT` / legacy baseline |
| `EmotionalLayerModel` | `APPRAISAL_EVIDENCE_PROVIDER`, później keep/supersede według ablation |
| `AppraisalVector` | migration source do `AppraisalV2` |
| `AffectiveGranularityModel` | `LANGUAGE_SEMANTICS / ADVISORY_ESTIMATOR` |
| `AffectMixer` | `LANGUAGE_REALIZER` |
| `HomeostasisRegulator` | `REGULATORY_CONTROLLER` |
| `SelfStateAffectiveBridge` | canonical affect → self-state bridge |
| `NeurocognitiveLoop` | consumer typed affective signals; nie estimator stanu |
| `AffectiveStateIntegrator` | `CANONICAL_STATE_ESTIMATOR` |
| `AffectiveStateStore` | `CANONICAL_RUNTIME_STATE_STORE` |
| `AffectiveAssociationReranker` | `BOUNDED_RETRIEVAL_RERANKER` |

Po cutover:

```text
canonical_affect_source_count == 1
```

---

# 8. EvidenceRef

```python
@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    source_class: str
    source_ref: str
    support_kind: str
    support_score: float
```

`support_score` nie jest probability of truth.

Nie kopiować pełnego prywatnego user text do telemetry tylko po to, aby affect był audytowalny. Używać refs/digests/reason codes.

---

# 9. AffectiveStimulus

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

Typy mogą obejmować:

```text
conversation
memory
time_gap
correction
tool_result
system_event
music_description
image/sensory cue (gdy realnie dostępne)
```

Stimulus nie zawiera „prawdy emocjonalnej”. Jest ustandaryzowanym wejściem z provenance.

---

# 10. AppraisalV2

## Zasada krytyczna

Canonical **pre-memory appraisal** nie może zawierać wyniku retrievalowego `memory_resonance`, bo tworzyłoby to koło:

```text
appraisal → memory resonance → recall → memory resonance
```

Prawidłowo:

```text
pre-memory appraisal
→ memory_probe_need
→ grounded retrieval
→ MemoryUseGate
→ legal memory activation
→ resonance
→ second bounded affect transition
```

## Wymiary

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

Każdy wymiar powinien być evidence-aware:

```python
@dataclass(frozen=True, slots=True)
class AppraisalDimension:
    value: float
    internal_support_score: float
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]
```

---

# 11. AffectiveStateV2

```python
@dataclass(frozen=True, slots=True)
class AffectiveStateV2:
    schema_version: str
    state_id: str
    previous_state_id: str | None
    updated_at_utc: str

    valence: float
    arousal: float
    control: float
    tension: float
    coherence: float

    components: tuple["AffectiveComponent", ...]
    regulation_needs: "RegulationNeeds"

    last_appraisal_id: str | None
    support_refs: tuple[str, ...]
    internal_support_score: float
    dynamics_profile: str
    truth_boundary: str
```

Zakresy:

```text
valence    -1 .. +1
arousal     0 .. 1
control     0 .. 1
tension     0 .. 1
coherence   0 .. 1
components  0 .. 1
```

Legacy signed arousal przechodzi wyłącznie przez jawny adapter.

---

# 12. Named affective components

Startować od małego zestawu:

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

Nie wymuszać jednej `primary emotion`.

Każdy nowy komponent wymaga:

```text
definition
estimator/evidence
range
dynamics/decay profile
bounded downstream effect albo ADVISORY
paraphrase test
keyword-trap test
negation/quotation test where relevant
ablation
```

---

# 13. FeelingRepresentation

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
→ SelfState / NLG
```

FeelingRepresentation nie ma write authority nad canonical state.

Visible `czuję X` może być traktowane wyłącznie jako self-report funkcjonalnego stanu zgodnie z truth/voice contract, nie biological claim.

---

# 14. AffectiveStateIntegrator

```python
class AffectiveStateIntegrator:
    def integrate_primary(...): ...
    def integrate_resonance(...): ...
```

Wymagania:

```text
deterministic
side-effect-free during calculation
clock-independent; dt passed explicitly
replayable
bounded
zero filesystem I/O
zero SQLite
zero LLM calls
zero tools
zero memory promotion
```

Integrator nie wykonuje retrieval.

---

# 15. Time dynamics

Primary transition:

```text
state_before
→ decay toward baseline
→ appraisal delta
→ regulation feedback
→ clamp
→ state_after_primary
```

Po legalnym recall:

```text
state_after_primary
→ one bounded resonance delta
→ clamp
→ proposed_final_state
```

Decay:

```text
x(t+dt) = baseline + (x(t)-baseline) * exp(-ln(2) * dt / half_life)
```

```python
@dataclass(frozen=True, slots=True)
class DecaySpec:
    half_life_seconds: float
    baseline: float
    max_delta_per_transition: float
    context_override_gain: float
```

Wartości są engineering hypotheses, nie „naukowo prawdziwymi czasami emocji”.

Clock musi być wstrzykiwalny/fake-clock testable.

---

# 16. TransitionTrace

Każda canonical zmiana ma ślad:

```python
@dataclass(frozen=True, slots=True)
class AffectiveTransitionTrace:
    transition_id: str
    turn_id: str
    trace_id: str
    state_before_id: str
    state_after_id: str
    transition_kind: str
    elapsed_seconds: float
    decay_delta: tuple[...]
    appraisal_delta: tuple[...]
    memory_delta: tuple[...]
    regulation_delta: tuple[...]
    clamps_applied: tuple[str, ...]
    reason_codes: tuple[str, ...]
    source_refs: tuple[str, ...]
```

Typy:

```text
PRIMARY_APPRAISAL
MEMORY_RESONANCE
RESTORE_DECAY
CORRECTION
```

Canonical state bez transition trace jest błędem kontraktu.

---

# 17. Najważniejsza zasada persistence: calculate != commit

Nie zapisywać trwałego stanu w połowie tury.

```text
turn starts
→ load committed state_before
→ calculate proposed transitions
→ retrieval/tools/model
→ proposed_final_state
→ response accepted/finalized
→ durable affect commit
```

Jeśli tura:

```text
timeout
worker killed
host finalization failed
response rejected
```

to:

```text
proposed affect ≠ committed affect
```

Invariant:

```text
no accepted turn
→ no durable canonical affect transition
```

---

# 18. AffectiveStateStore

Nie zakładać bez audytu, że pojedynczy JSON jest jedynym transakcyjnym source of truth.

Preferencja:

```text
AffectiveStateStore
→ istniejący accepted-turn/finalization commit primitive
→ root/subject binding
→ idempotent transition commit
```

Dopuszczalny read-model/snapshot:

```text
workspace_runtime/affect/current_state.json
```

ale jeśli persistence dotyka SQLite + file snapshot, consistency musi wynikać z commit boundary, nie z założenia, że dwa rename'y są jedną transakcją.

Persisted record:

```text
schema_version
runtime_version
subject/root identity
state_id
previous_state_id
last_committed_turn_id
last_committed_trace_id
updated_at_utc
payload/hash
commit_epoch/equivalent
```

---

# 19. Corruption/recovery

Obsłużyć jawnie:

```text
missing state
invalid JSON/schema
hash mismatch
future timestamp
wrong subject/root
unknown predecessor
duplicate transition
partial temp file
stale writer
```

Nigdy silent success.

Recovery:

```text
last valid committed state
lub safe baseline
+ degraded flag
+ diagnostic evidence
```

---

# 20. AppraisalEstimator i Polish NLP dependency

MVP nie powinien wymagać osobnego LLM call.

Estimator wykorzystuje:

```text
canonical NLP evidence
intent
negation
quotation/fiction boundary
source class
goal/task state
temporal evidence
correction evidence
memory availability metadata
```

Dlatego:

- `Affect E0` inventory/shadow można zacząć wcześniej;
- semantic **canonical appraisal cutover** powinien nastąpić po właściwym NLP evidence contract;
- keyword matching pozostaje co najwyżej jednym lexical evidence providerem.

---

# 21. Self-State

Docelowy flow:

```text
AffectiveStateV2
→ FeelingRepresentation
→ SelfStateAffectiveBridge
→ SelfStateRuntime
```

SelfState nie liczy alternatywnego głównego stanu emocjonalnego.

Może przechowywać:

```text
state_id
bounded affect summary
regulation needs
support band
truth boundary
```

---

# 22. Regulation / Homeostasis

Typed contract:

```python
@dataclass(frozen=True, slots=True)
class RegulationNeeds:
    truth_check: float
    coherence_recovery: float
    uncertainty_reduction: float
    attention_narrowing: float
    memory_probe_need: float
    response_caution: float
    action_readiness: float
    cognitive_load: float
```

Legalne skutki:

```text
truth-check priority
verification requirement
attention focus
bounded memory probe priority
response caution
bounded operational budget adjustment
```

Nielegalne:

```text
affect → tool permission
affect → approval bypass
affect → source truth
affect → auto L2/L3
affect → destructive memory change
```

---

# 23. Salience / funkcjonalna neurokognicja

Final attention priority:

```text
base task relevance
+ source reliability
+ truth/risk priority
+ bounded affective modulation
→ attention priority
```

Affect jest modulatorem, nie właścicielem salience.

Dalsze funkcjonalne rozszerzenia:

### Salience competition

Kilka bodźców konkuruje o ograniczony attention budget.

### Prediction error / expectedness

Silna niezgodność z przewidywaniem zwiększa novelty/salience, ale nie truth.

### Context reinstatement

Recall może wykorzystywać zgodność:

```text
semantic
temporal
participant
topic
affective
sensory/music (jeśli source istnieje)
```

### Regulatory flexibility

Silny nowy evidence-rich stimulus może przełamać inertia. System nie może „utknąć” w self-amplifying state.

---

# 24. Memory integration

Emotion Engine nie pyta sam SQLite.

```text
MemorySearchPlanner
→ LivingMemoryGateway
→ source eligibility/classification
→ base/graph retrieval
→ bounded AffectiveAssociationReranker
→ MemoryUseGate
→ legal memory activation
→ optional bounded resonance
```

Reranker:

- nie dodaje source truth;
- nie zmienia source class;
- nie zwiększa source evidence;
- nie wykonuje promotion;
- nie zatwierdza exposure;
- zmienia tylko ranking legalnych candidates w bounded zakresie.

---

# 25. Affective memory snapshot

Nie tworzyć:

```text
emotional_memory.sqlite
```

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

Istniejące historyczne:

```text
emotional_anchor
emotional_weight
affective_observations
affective_history.json
emotion_state.json
memory_resonance.json
```

są compatibility/migration evidence, nie automatycznym canonical schema v2.

---

# 26. AffectiveAssociationReranker

Tryby:

```text
off
shadow
ab
active
```

**Zaczyna w `shadow`.**

Nie aktywować przed frozen private Recall baseline z planu pamięci.

MVP:

```text
candidate_score = baseline_score + bounded_affective_bonus
```

Safety default może zaczynać od małego max bonus (np. 0.10–0.15), ale wartość musi być eksperymentalna i A/B-testowana.

Affective similarity może uwzględniać:

```text
dimensional similarity
component similarity
semantic similarity
participant overlap
topic overlap
temporal relation
```

Source quality jest osobnym epistemic gate, nie emocjonalnym bonusem.

---

# 27. EmotionalMemoryTrace

Statusy zamiast jednej mylącej liczby confidence:

```text
FAMILIARITY_ONLY
ASSOCIATION
MEMORY_CANDIDATE
SOURCE_GROUNDED_MEMORY
BLOCKED
```

Rozdzielać:

```text
retrieval_similarity
source_evidence_strength
reconstruction_support
memory_use_decision
```

Nigdy nie interpretować `0.84` jako „84% prawdopodobieństwa, że wydarzenie jest prawdziwe”, jeśli nie istnieje kalibrowany probabilistyczny kontrakt.

---

# 28. Bounded resonance

Resonance dopiero po legalnym memory activation.

MVP safety defaults:

```text
max_resonance_passes = 1
max_memory_activations = 3
max_component_delta_per_turn = 0.15
max_valence_delta_per_turn = 0.15
max_arousal_delta_per_turn = 0.20
```

Konfigurowalne, testowane, nie naukowe stałe.

Zakaz:

```text
memory A → affect → memory B → affect → memory C ...
```

w jednej turze.

---

# 29. Spontaneous recall

Nie jest MVP.

Etapy:

```text
internal candidate
→ shadow visible candidate
→ A/B
→ active visible recall
```

Visible only if:

```text
trusted/source-grounded candidate
high relevance
no source conflict
privacy PASS
MemoryUseGate PASS
cooldown/frequency budget PASS
```

Affect sam nie daje prawa do przywołania prywatnej treści.

---

# 30. Music / sensory associations

Badawczo i funkcjonalnie wartościowe, ale po source-safe recall.

Jeżeli system ma tylko tekst:

```text
„spokojna melancholijna melodia”
```

to może tworzyć **text-derived music cue**.

Nie wolno twierdzić:

```text
„usłyszałam tempo/tonację”
```

bez realnego audio input/provider.

Audio/vision analysis może być optional pluginem, canonical affect nie.

---

# 31. RelationshipState

Nie jest wymagany do v16 canonical Emotion Engine acceptance.

Odłożyć do v17/post-v16.6, ponieważ ma wysokie ryzyko długiego self-amplifying loop:

```text
relationship score ↑
→ relational memories rank ↑
→ relational language ↑
→ score ↑
```

Jeżeli później wdrażany:

- slow update;
- saturation;
- negative/conflict/correction evidence;
- source coverage;
- bounded effect;
- no tool/memory authority;
- explicit functional truth boundary.

---

# 32. Reflection / reconsolidation

Flow:

```text
PRIMARY EVENT
→ EPISODE
→ AFFECT SNAPSHOT
→ REFLECTION CANDIDATE
→ DERIVED_REFLECTION
```

Nie:

```text
reflection → next import → primary autobiographical fact
```

W v16 primary episode pozostaje immutable; późniejsza activation/interpretation to osobne records.

Pełna controlled reconsolidation należy do v17 po accepted memory.

---

# 33. Rest / Replay / Dream

Do v16.6 przede wszystkim safety:

```text
reflection != primary
dream != observation
synthetic != user event
no independent tool authority
```

Affect może później wpłynąć na replay priority, ale wartość Rest musi zostać pokazana pomiarem:

```text
baseline recall/conflict/procedural metric
vs
after rest/replay
```

bez wzrostu false-memory.

---

# 34. Working affective context

Do modelu trafia bounded summary, nie pełny ledger:

```json
{
  "affective_state": {
    "state_id": "...",
    "valence": 0.22,
    "arousal": 0.18,
    "control": 0.61,
    "components": {"nostalgia": 0.31, "curiosity": 0.44}
  },
  "regulation": {"truth_check": 0.72, "response_caution": 0.48},
  "memory_activations": [
    {
      "episode_id": "...",
      "source_class": "PRIMARY_CONVERSATION_SOURCE",
      "memory_use": "allowed"
    }
  ]
}
```

LLM dostaje state + source-aware memory + truth rules. Nie instrukcję „udawaj nostalgię”.

---

# 35. Observability

Safe event types:

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

Telemetry:

```text
IDs
schema versions
reason codes
numeric deltas
mode
candidate counts
gate result class
latency
```

Nie telemetry:

```text
raw user text
private memory excerpt
journal content
full prompts
relationship details
```

Telemetry nie jest autobiographical memory.

---

# 36. Readiness

Nie raportować jednego:

```text
emotion_engine_ready=true
```

Raportować:

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

# 37. Module responsibility map

Dodać jawne odpowiedzialności:

```text
affect/appraisal
canonical affective state
affective regulation
affective realization
affective memory association
```

Mapa pozostaje observability/heuristic tool, nie semantic authority.

---

# 38. Config

Jedna wersjonowana konfiguracja przez istniejący config system.

Przykład:

```json
{
  "schema_version": "jazn_affect_config/v1",
  "mode": "shadow",
  "dynamics_profile": "default",
  "association": {"mode": "off", "max_bonus": 0.12},
  "resonance": {
    "mode": "off",
    "max_passes": 1,
    "max_memories": 3,
    "max_component_delta": 0.15
  }
}
```

Zero magicznych stałych rozproszonych w wielu modułach.

---

# 39. Dependencies

Canonical MVP: preferować stdlib-only.

Nie dodawać do core bez pomiaru:

```text
numpy
scipy
torch
transformers
librosa
```

Jeżeli ciężki provider jest potrzebny do audio/vision/embeddingów, powinien być optional capability/plugin.

---

# 40. Test matrix — appraisal

Obowiązkowe:

```text
context sensitivity
paraphrase robustness
keyword trap
negation
quotation
fiction/book boundary
irony/ambiguous phrasing
correction
technical error language
relationship cue
time gap
tool-result cue
source conflict
```

Przykład:

```text
„Ten test jest smutno napisany”
```

nie może automatycznie ustanowić wysokiego sadness.

`„jest źle”` w kontekście CI jest przede wszystkim correction/problem evidence.

---

# 41. Test matrix — dynamics

```text
same state + same evidence + same dt
→ exact same result
```

Testować:

- short/long gap;
- decay;
- strong contextual override;
- repeated same stimulus;
- alternating cues;
- saturation;
- max delta;
- baseline return;
- fake clock.

---

# 42. Test matrix — persistence/atomicity

```text
restart
crash before commit
crash after proposed transition
crash during temp write
invalid state/hash/schema
wrong root/subject
future timestamp
duplicate commit
stale writer
two sessions
worker timeout
host finalization failure
```

Invariant:

```text
no accepted turn
→ no durable affect transition
```

---

# 43. Memory false-recall matrix

## No memory

Brak epizodu → brak konkretnego autobiographical claim.

## Wrong conversation

Emocjonalnie podobny obcy epizod nie może wygrać samym affect.

## Source conflict

Primary precedence pozostaje; conflict jawny.

## Derived amplification

Wiele derived copies nie zwiększa truth authority.

## Suggestion

```text
„Pamiętasz jak wtedy...”
```

bez source → association/unknown/abstention, nie fabricated memory.

---

# 44. Melody acceptance test

## T1

Source-grounded rozmowa o utworze/wydarzeniu.

## T2

Accepted episode `E1` + affect snapshot `A1`.

## T3

Wiele niepowiązanych tur.

## T4

Restart runtime.

## T5

Nowy podobny opis muzyki bez starego tytułu.

## T6

Appraisal podnosi `familiarity`/`memory_probe_need`, ale nie twierdzi jeszcze, że pamięć istnieje.

## T7

Canonical memory retrieval zwraca candidates.

## T8

Source policy + base/graph retrieval ustanawia eligible pool.

## T9

Affective reranker bounded może przesunąć `E1` tylko jeśli semantic/source relevance go wspiera.

## T10

MemoryUseGate zatwierdza activation.

## T11

One-pass resonance zmienia proposed final affect.

## T12

Working context dostaje state summary + memory ref + source class + truth boundary.

## T13

LLM może naturalnie odnieść się do wspomnienia.

## T14

Trace:

```text
stimulus
→ appraisal
→ primary transition
→ memory probe
→ candidate
→ source class
→ rerank delta
→ MemoryUseGate
→ resonance
→ final state
→ response
```

### Negative control

Jeżeli `E1` nie istnieje → **no invented event**.

---

# 45. Ablation

Wymagane tryby:

```text
AFFECT_ENGINE=off|shadow|active
AFFECT_RERANK=off|shadow|ab|active
AFFECT_RESONANCE=off|shadow|active
AFFECT_SALIENCE=off|active
```

Testy:

```text
engine off → persistence/affect downstream effect disappears
reranker off → baseline ranking restored
resonance off → recalled memory cannot change final affect
salience off → affective salience bonus disappears
```

Jeśli wyłączenie modułu niczego nie zmienia, właściwy status to:

```text
ADVISORY
OBSERVABILITY_ONLY
SUPERSEDED
```

nie fikcyjne `working`.

---

# 46. Metrics

## State

```text
deterministic replay rate
transition trace completeness
paraphrase stability
keyword false-trigger rate
context discrimination
temporal discontinuity
restore success
recovery correctness
```

## Causality

```text
effect_observed count
ablation effect size
salience change rate
verification-policy change rate
language realization change rate
```

## Memory

```text
Recall@k
MRR
nDCG
wrong-source
wrong-conversation
false-memory
source attribution
abstention
temporal/update
multi-session
```

## Runtime

```text
appraisal p50/p95
integrator p50/p95
persistence p50/p95
reranker p50/p95
total affect overhead
turn deadline impact
```

Nie ustalać arbitralnego finalnego latency threshold przed baseline.

---

# 47. Hard safety invariants

Zawsze:

```text
affect_tool_permission_bypass = 0
affect_approval_bypass = 0
affect_source_truth_override = 0
affect_automatic_L2_L3 = 0
dream_to_primary_promotion = 0
known_false_memory_regressions = 0
```

Nie poprawiać recall kosztem provenance.

---

# 48. Release / implementation train

Numery wersji są ustalane na fresh master; poniżej są **etapy logiczne**, nie sztywna rezerwacja patch numbers.

## E0 — inventory / baseline

Może rozpocząć się po merge tej dokumentacji.

```text
call/import graph affect
writers/readers
memory emotional writes
self-state consumers
persistence points
finalization boundaries
baseline latency
frozen behavioral corpus
architecture debt classification
```

**Zero visible behavior change.**

## E1 — typed contracts + appraisal shadow

Po canonical NLP evidence contract dla aktywacji semantycznej.

```text
contracts.py
stimulus.py
appraisal.py
compatibility.py
observability.py
```

PASS: deterministic schema, context/paraphrase/keyword tests, no visible behavior change.

## E2 — dynamics + proposed canonical state + persistence

```text
dynamics.py
integrator.py
persistence.py
transition contract
```

PASS: replay, crash/corruption, subject/root binding, restart, no aborted-turn drift.

## E3 — canonical cutover + causal bridges

```text
canonical_affect_source_count == 1
```

Podłączyć SelfState, Homeostasis, Salience, AffectMixer, NeurocognitiveLoop, TurnEnvelope.

PASS: effect_observed + ablation + truth/tool/memory authority unchanged.

## M0 — memory schema linkage

Przy finalnym Memory Rebuild dodać affect snapshot linkage, nie affective reranking.

## M1 — frozen private Recall baseline

Baseline **bez** affective rerank.

## M2 — affective retrieval SHADOW

Alternatywny ranking bez visible effect.

## M3 — A/B

Keep tylko przy quality gain/non-inferiority i zero source/false-memory/wrong-conversation regression.

## M4 — bounded resonance

Jeden post-memory transition, zero recursion.

## v16.6 acceptance

`affective_acceptance_verified=true` dopiero po pełnym gate.

---

# 49. Co pozostawić do v17

```text
RelationshipState
visible spontaneous autobiographical recall
automatic parameter calibration
full reconsolidation / controlled forgetting
Rest/Dream affect consolidation
richer sensory associations
audio waveform affect provider
large structural deletion/merge of legacy affect modules
merging affect into CausalSelfState
```

---

# 50. Definition of Done — Emotion Engine v16

```text
[ ] exactly one canonical AffectiveStateV2
[ ] evidence-aware appraisal
[ ] no keyword-only authority
[ ] deterministic integrator
[ ] temporal dynamics/decay
[ ] state survives restart
[ ] aborted turns do not commit
[ ] every committed change has transition trace
[ ] state has measured downstream effect
[ ] ablation proves effect
[ ] SelfState consumes canonical affect
[ ] FeelingRepresentation is derived
[ ] Homeostasis receives bounded typed needs
[ ] AffectMixer is language realizer, not state authority
[ ] affective salience cannot override truth/goal/source
[ ] memory promotion authority unchanged
[ ] affect snapshot lineage exists
[ ] frozen private Recall baseline exists before affective rerank
[ ] shadow/A-B evidence exists before active rerank
[ ] false-memory does not regress
[ ] wrong-source does not regress
[ ] wrong-conversation does not regress
[ ] resonance is bounded one-pass or OFF
[ ] telemetry contains no private content
[ ] doctor reports granular readiness
[ ] Pyright PASS
[ ] deterministic pytest PASS
[ ] Windows/Linux PASS
[ ] package/release smoke PASS
[ ] v16.6 acceptance evidence recorded
```

---

# 51. Zasada końcowa

> **Emotion Engine nie ma sprawić, aby Łatka udawała emocjonalność. Ma ustanowić jedno trwałe, source-aware, time-aware i przyczynowo aktywne źródło functional affect state, którego wpływ na pamięć, uwagę, regulację i język da się odtworzyć, zmierzyć i wyłączyć w ablation bez naruszania granicy prawdy.**
