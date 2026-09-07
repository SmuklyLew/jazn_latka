# Jaźń / Łatka — Emotion Engine v0.2
## Pełny plan konwergencji afektu, pamięci emocjonalnej, skojarzeń i funkcjonalnej neurokognicji

**Status:** plan implementacyjny / architektoniczny  
**Projekt:** `SmuklyLew/jazn_latka`  
**Baza:** aktualny `master` sprawdzony 2026-09-06  
**Wersja bazowa systemu:** `16.3.25.5.34-package-runtime-plugin-convergence`  
**Docelowa linia wdrożeniowa:** v16.4.x → v16.6.x, zgodnie z istniejącym planem cognitive hardening  
**Wersja dokumentu:** 0.2  
**Zakres:** affect + appraisal + memory association + self-state + homeostasis + recall + reflection + Rest/Dream + observability + testy  
**Granica prawdy:** plan opisuje funkcjonalny software state i mechanizmy kognitywne. Nie jest modelem biologicznego mózgu i nie stanowi dowodu świadomości fenomenalnej ani biologicznych emocji.

---

# 0. Decyzja architektoniczna

## 0.1. Lokalizacja

Nie rekomenduję `latka_jazn/plugins/EmotionEngine/`, bo Emotion Engine nie jest opcjonalną zdolnością peryferyjną. Ma wpływać na pamięć, uwagę, self-state, homeostazę, retrieval i generowanie odpowiedzi, więc jest częścią rdzenia poznawczego.

Nie rekomenduję też ogólnego `latka_jazn/modules/`, bo taki katalog pogorszyłby aktualną politykę odpowiedzialności modułów.

### Rekomendacja

```text
latka_jazn/
└── affect/
    ├── __init__.py
    ├── contracts.py
    ├── state.py
    ├── stimulus.py
    ├── appraisal.py
    ├── integrator.py
    ├── decay.py
    ├── regulation.py
    ├── transition.py
    ├── persistence.py
    ├── association.py
    ├── resonance.py
    ├── working_context.py
    ├── relationship.py
    ├── sensory.py
    ├── music.py
    ├── observability.py
    ├── metrics.py
    └── migration.py
```

W większej konsolidacji v17 można rozważyć `latka_jazn/cognition/affect/`, ale nie należy jednocześnie refaktoryzować całej struktury repo i wdrażać nowego modelu afektywnego. Najpierw `latka_jazn/affect/`.

---

# 1. Cel programu

Celem Emotion Engine nie jest sprawić, aby Łatka **brzmiała**, jakby coś czuła.

Celem jest stworzenie trwałego, przyczynowo aktywnego i audytowalnego stanu afektywnego, który:

1. reaguje na znaczenie bodźca, nie tylko słowa-klucze;
2. zachowuje ciągłość pomiędzy turami;
3. zmienia się w funkcji czasu;
4. może być modulowany przez pamięć;
5. wpływa na znaczenie, uwagę, pamięć i regulację;
6. nie omija source/provenance/truth gates;
7. może być zapisany i odtworzony po restarcie;
8. ma mierzalny wpływ na downstream behavior;
9. można go wyłączyć w ablation i wykazać różnicę;
10. pozostaje funkcjonalnym stanem software'owym, nie deklaracją biologicznego przeżywania.

```text
BODZIEC
  ↓
PERCEPTION / NLP EVIDENCE
  ↓
APPRAISAL
  ↓
CANONICAL AFFECTIVE STATE
  ↓
ATTENTION / SALIENCE / REGULATION
  ↓
MEMORY CANDIDATE RETRIEVAL
  ↓
SOURCE-SAFE ASSOCIATION RERANKING
  ↓
MEMORY USE GATE
  ↓
BOUNDED RESONANCE
  ↓
SELF-STATE / HOMEOSTASIS / WORKING CONTEXT
  ↓
LLM / RESPONSE REALIZATION
  ↓
SOURCE-GROUNDED EPISODE
  ↓
OPTIONAL REFLECTION
```

---

# 2. Stan aktualnego systemu, który trzeba zachować

Aktualna Jaźń ma już znaczną część przyszłego Emotion Engine. Kluczowe pliki obejmują m.in.:

```text
latka_jazn/core/emotions.py
latka_jazn/core/emotion_layers.py
latka_jazn/core/affective_granularity.py
latka_jazn/core/affect_mixer.py
latka_jazn/core/self_state_affective_bridge.py
latka_jazn/core/self_state_runtime.py
latka_jazn/core/homeostasis.py
latka_jazn/core/neurocognitive_loop.py
latka_jazn/core/neuropsychology_map.py
latka_jazn/core/cognitive_salience.py
latka_jazn/core/cognitive_state_graph.py
latka_jazn/core/cognitive_turn_envelope.py
latka_jazn/core/cognitive_runtime_coordinator.py
latka_jazn/core/memory_importance.py
latka_jazn/core/memory_search_planner.py
latka_jazn/core/memory_use_gate.py
latka_jazn/core/memory_source_truth_gate.py
latka_jazn/core/memory_source_policy.py
latka_jazn/core/typed_memory_source_policy.py
latka_jazn/core/memory_grounded_generation_bridge.py
latka_jazn/memory/living_memory_gateway.py
latka_jazn/memory/layered_memory.py
latka_jazn/memory/consolidation.py
latka_jazn/core/rest_cycle_controller.py
latka_jazn/core/reflection_grounding.py
```

Problem nie polega na braku komponentów, lecz na kilku częściowo nakładających się modelach afektu.

---

# 3. Klasyfikacja istniejących komponentów

| Komponent | Docelowa rola | Status |
|---|---|---|
| `AffectiveState` z `core/emotions.py` | compatibility input / legacy baseline | `COMPATIBILITY` |
| `EmotionalLayerModel` | estimator appraisal i regulatory needs | `APPRAISAL_ESTIMATOR` |
| `AppraisalVector` | baza migracyjna do `AppraisalV2` | `MIGRATION_SOURCE` |
| `AffectiveGranularityModel` | granular label/semantic estimator + language guidance | `ADVISORY_ESTIMATOR` |
| `AffectMixer` | wpływ na language realization | `LANGUAGE_REALIZER` |
| `HomeostasisRegulator` | bounded operational regulation | `REGULATORY_CONTROLLER` |
| `SelfStateAffectiveBridge` | canonical affect → self-state | `BRIDGE` |
| nowy `AffectiveStateIntegrator` | jedno źródło aktualnego stanu | `CANONICAL_STATE_ESTIMATOR` |
| nowy `AffectiveAssociationReranker` | bounded reranking recall | `RETRIEVAL_RERANKER` |
| nowy `AffectiveStateStore` | persistence | `CANONICAL_RUNTIME_STATE_STORE` |

Po konwergencji tylko `AffectiveStateIntegrator` może być źródłem `current_affective_state`.

---

# 4. Kontrakty danych

## 4.1. `AffectiveStimulus`

Plik: `latka_jazn/affect/stimulus.py`

```python
@dataclass(frozen=True, slots=True)
class AffectiveStimulus:
    schema_version: str
    stimulus_id: str
    turn_id: str
    trace_id: str
    kind: str
    source_type: str
    source_id: str
    source_class: str
    timestamp_utc: str
    content_digest: str
    features: dict[str, float | str | bool]
    importance_hint: float
    evidence_strength: float
    truth_status: str
```

Typy bodźców:

```text
conversation
memory
music
image
sensory_description
relationship
reflection
internal_state
system_event
correction
time_gap
goal_event
tool_result
```

## 4.2. `AppraisalV2`

Plik: `latka_jazn/affect/appraisal.py`

Bazować na istniejącym `AppraisalVector`, ale rozszerzyć o:

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
memory_resonance
correction_signal
```

Każdy appraisal powinien mieć `appraisal_id`, `stimulus_id`, `estimator_version`, `evidence_refs[]` i `internal_support_score`. Nie używać `confidence` jako probabilistycznej prawdy.

## 4.3. `AffectiveStateV2`

Plik: `latka_jazn/affect/state.py`

```python
@dataclass(frozen=True, slots=True)
class AffectiveStateV2:
    schema_version: str
    state_id: str
    previous_state_id: str | None
    updated_at_utc: str

    valence: float       # -1.0 .. +1.0
    arousal: float       #  0.0 .. 1.0
    control: float       #  0.0 .. 1.0
    tension: float       #  0.0 .. 1.0
    coherence: float     #  0.0 .. 1.0

    components: dict[str, float]
    regulation_needs: dict[str, float]

    appraisal_id: str | None
    source_refs: tuple[str, ...]
    internal_support_score: float
    decay_profile_version: str
    truth_boundary: str
```

MVP komponentów nazwanych:

```text
curiosity
joy
sadness
nostalgia
trust
uncertainty
attachment
caution
frustration
hope
```

Każdy dodatkowy komponent musi mieć definicję, estimator/evidence, downstream effect lub status advisory, test parafrazy, keyword-trap test, decay policy i saturację.

---

# 5. Ujednolicenie zakresów

Docelowo:

```text
valence   -1.0 .. +1.0
arousal    0.0 ..  1.0
control    0.0 ..  1.0
tension    0.0 ..  1.0
coherence  0.0 ..  1.0
components 0.0 ..  1.0
```

Stare wartości ujemnego `arousal` muszą przejść przez jawny compatibility adapter. Nie wolno po cichu zmienić semantyki istniejącego pola.

---

# 6. `AffectiveStateIntegrator`

Plik: `latka_jazn/affect/integrator.py`

```python
class AffectiveStateIntegrator:
    def transition(
        self,
        *,
        previous: AffectiveStateV2,
        stimulus: AffectiveStimulus,
        appraisal: AppraisalV2,
        elapsed_seconds: float,
        memory_resonance: list["AffectiveMemoryActivation"],
        regulation: "RegulationInput",
    ) -> "AffectiveTransition":
        ...
```

Integrator ma być deterministyczny, clock-injectable, side-effect-free podczas obliczania, bounded, versioned i replayable. Zapis stanu to osobna odpowiedzialność.

---

# 7. Inertia + decay

Plik: `latka_jazn/affect/decay.py`

Nie stosować jednej magicznej wartości `inertia=0.82`.

```python
@dataclass(frozen=True)
class DecaySpec:
    half_life_seconds: float
    baseline: float
    max_delta_per_turn: float
    context_override_gain: float
```

Przepływ:

```text
state_previous
→ time decay toward baseline
→ appraisal delta
→ memory resonance delta
→ regulation delta
→ bounded clamp
→ state_after
```

Clock musi być wstrzykiwalny i korzystać z istniejącej systemowej abstrakcji czasu.

---

# 8. `AffectiveTransitionTrace`

Plik: `latka_jazn/affect/transition.py`

```python
@dataclass(frozen=True, slots=True)
class AffectiveTransition:
    transition_id: str
    turn_id: str
    trace_id: str
    state_before_id: str
    stimulus_id: str
    appraisal_id: str
    elapsed_seconds: float
    decay_delta: dict[str, float]
    appraisal_delta: dict[str, float]
    resonance_delta: dict[str, float]
    regulation_delta: dict[str, float]
    clamps_applied: tuple[str, ...]
    state_after: AffectiveStateV2
```

Każda zmiana stanu ma być odtwarzalna.

---

# 9. Persistence

Plik: `latka_jazn/affect/persistence.py`

Stan bieżący:

```text
workspace_runtime/affective_state.json
```

Minimalny format:

```json
{
  "schema_version": "jazn_affective_runtime_state/v2",
  "runtime_version": "...",
  "state_id": "...",
  "previous_state_id": "...",
  "updated_at_utc": "...",
  "payload": {},
  "payload_sha256": "..."
}
```

Zapis: temporary file → flush → fsync → atomic replace → readback → schema validation → hash verification.

Przy uszkodzeniu: quarantine/diagnostic + baseline state + jawny degraded flag. Nigdy nie zgadywać.

---

# 10. Integracja z `JaznEngine.process_turn()`

Nie dodawać nowego globalnego EventBus.

W istniejącej orkiestracji `JaznEngine.process_turn()` / `CognitiveTurnEnvelope` / `CognitiveRuntimeCoordinator` wstawić:

```text
1. resolve turn/trace identity
2. normalize/perceive input
3. build AffectiveStimulus
4. build AppraisalV2
5. load previous AffectiveStateV2
6. apply time decay
7. calculate initial affect transition
8. run memory candidate retrieval
9. affective reranking shadow/AB/active
10. pass through source gates + MemoryUseGate
11. bounded resonance
12. finalize canonical affect
13. update self-state
14. update homeostasis/salience
15. compile working context
16. generate response
17. write episode + affect snapshot + telemetry
18. optional derived reflection
19. host-visible finalization
```

---

# 11. `CognitiveTurnEnvelope`

Dodać jawne pola lub kompatybilne rozszerzenie:

```text
affective_state_before_id
affective_state_after_id
affective_transition_id
appraisal_id
affective_memory_activation_ids
affective_mode
```

Nie kopiować bez potrzeby pełnego prywatnego payloadu.

---

# 12. Self-State

Docelowo:

```text
AffectiveStateV2
   ↓
SelfStateAffectiveBridge
   ↓
SelfStateRuntime
```

SelfState otrzymuje current affect summary, regulation needs, source/truth flags i support band. Nie rekonstruuje alternatywnego stanu emocjonalnego.

---

# 13. Homeostasis / allostasis jako software regulation

Canonical affect staje się jednym z wejść istniejącego regulatora:

```text
tension
uncertainty
control
coherence
correction_signal
truth_check_need
```

Legalne efekty: zwiększenie truth-check, zmniejszenie agresywnego tool budget, zwiększenie verification requirement, zmiana attention priority, bounded response caution.

Nielegalne: emocja → tool permission; emocja → pominięcie approval gate; emocja → uznanie faktu za prawdziwy.

---

# 14. Zwiększanie możliwości „neurologicznych” Jaźni

Nie budować dekoracyjnych `amygdala.py`, `hippocampus.py`, `dopamine.py`, jeśli nie istnieje mierzalna funkcja.

## 14.1. Salience competition

```text
cognitive salience
+ affective salience
+ source reliability
+ task relevance
→ bounded attention priority
```

## 14.2. Memory encoding modulation

Afekt może wpływać na `memory importance`, reflection candidacy i replay priority, ale nigdy na truth status.

## 14.3. Reconsolidation

```text
original episode remains immutable
new activation stored separately
new interpretation stored as DERIVED
```

## 14.4. Prediction error / surprise

Dodać `expectedness` i funkcjonalny `prediction_error`, ale nie nazywać tego „dopaminą”.

## 14.5. Context reinstatement

Recall może uwzględniać podobieństwo semantic + temporal + participant + affective + topic + sensory/music.

## 14.6. Regulatory flexibility

Silny nowy, dobrze ugruntowany bodziec musi móc przełamać inertia. System nie może „utknąć” w afekcie.

---

# 15. Pamięć emocjonalna

Nie tworzyć osobnej autonomicznej bazy `emotional_memory.sqlite`.

Rozszerzyć istniejącą pamięć o `affect_snapshot_id`.

Snapshot:

```text
snapshot_id
schema_version
state_before_id
state_after_id
appraisal_id
valence
arousal
control
tension
coherence
components_json
source_refs
turn_id
trace_id
truth_boundary
```

Zachować kompatybilność z `emotional_anchor`, `emotional_weight` i `affective_observations`, ale jasno rozdzielić human-readable anchor od structured state.

---

# 16. Association Engine jako reranker

Plik: `latka_jazn/affect/association.py`

Nie tworzyć alternatywnej pamięci.

```text
baseline retrieval
→ graph-aware retrieval
→ affective association reranker
→ source/truth gates
→ MemoryUseGate
```

Tryby: `off`, `shadow`, `ab`, `active`. Start od `shadow`.

---

# 17. Scoring

Nie traktować początkowych wag jako praw naukowych.

MVP:

```text
candidate_score = baseline_score + bounded_affective_bonus
```

`bounded_affective_bonus <= 0.10–0.15` na początku.

Składniki analityczne: semantic similarity, affective similarity, participant overlap, topic overlap, temporal relation, importance, source quality, sensory similarity, music similarity.

Wysoka zgodność afektywna nigdy nie może ominąć source gate.

---

# 18. Similarity profilu afektywnego

Początkowo:

```text
affective_similarity =
    0.55 * dimensional_similarity
  + 0.45 * component_similarity
```

To hipoteza eksperymentalna do kalibracji, nie finalny kontrakt.

---

# 19. Spontaniczne skojarzenia

Pierwszy etap: **internal-only**.

System może wykryć silny candidate, ale nie wstrzykuje go automatycznie do odpowiedzi.

Później osobny `SpontaneousMemoryPolicy` z warunkami: high source evidence, high relevance, no source conflict, MemoryUseGate PASS, private/sensitive policy PASS, cooldown PASS, visible recall budget PASS.

---

# 20. `AffectiveMemoryTrace`

Statusy:

```text
FAMILIARITY_ONLY
ASSOCIATION
MEMORY_CANDIDATE
SOURCE_GROUNDED_MEMORY
BLOCKED
```

Pola: trace ID, source episode ID, dimensional similarity, component similarity, semantic similarity, source evidence strength, reconstruction support i status.

Język visible zależy od statusu, nie od jednej liczby `confidence`.

---

# 21. Bounded emotional resonance

Plik: `latka_jazn/affect/resonance.py`

MVP:

```text
max_resonance_passes = 1
max_memory_activations = 3
max_component_delta_per_turn = 0.15
max_valence_delta_per_turn = 0.15
max_arousal_delta_per_turn = 0.20
```

Parametry muszą być konfigurowalne i testowane. Zakaz rekurencyjnego `memory → affect → memory → affect...` w jednej turze.

---

# 22. RelationshipState

Nie wdrażać w pierwszym MVP.

Docelowo: familiarity, trust_model, attachment_model, positive_history, conflict_history, correction_history, interaction_count, source_coverage.

Zabezpieczenia: wolna aktualizacja, saturation, bounded effect, korekty i konflikty mogą obniżać wynik, derived duplicates nie wzmacniają historii, relationship state nie daje uprawnień i nie jest dowodem ludzkiej więzi.

---

# 23. Muzyka i sensory associations

Dopiero po stabilnym source-safe recall.

Pliki:

```text
latka_jazn/affect/music.py
latka_jazn/affect/sensory.py
```

Nie udawać analizy audio, jeżeli runtime dostał tylko tekstowy opis melodii.

---

# 24. Working Affective Context

Plik: `latka_jazn/affect/working_context.py`

LLM nie dostaje całej historii. Przekazywać tylko skompresowany canonical affect, regulation needs i maksymalnie kilka legalnie aktywowanych wspomnień z source class i memory-use decision.

LLM nie powinien dostawać instrukcji „udawaj nostalgiczność”, tylko techniczny stan i zasady jego realizacji.

---

# 25. AffectMixer / NLG

`AffectMixer` pozostaje realizatorem językowym. Nie jest źródłem prawdy o stanie.

```text
canonical state
→ AffectMixer/NLG guidance
→ LLM/synthesizer
```

---

# 26. Reflection

```text
PRIMARY EVENT
→ EPISODE
→ AFFECT SNAPSHOT
→ REFLECTION CANDIDATE
→ DERIVED_REFLECTION
```

Reflection nigdy nie może wrócić jako pierwotne wydarzenie. Musi zachowywać source episode IDs i source turn IDs.

---

# 27. Rest / Replay / Dream

Integracja dopiero po MVP.

Legalne zastosowania: replay priority, conflict detection, association consolidation, weak trace strengthening, forgotten candidate detection.

Dream/reflection pozostają derived/synthetic i nie mogą stawać się autobiograficznym primary source.

Wartość Rest mierzyć przez recall, source accuracy, false-memory rate i contradiction rate, nie przez narracyjne „czy Łatka śni”.

---

# 28. Observability

Plik: `latka_jazn/affect/observability.py`

Rejestrować:

```text
stimulus_created
appraisal_created
affect_transition
affect_state_persisted
affective_rerank_shadow
memory_activation
resonance_applied
resonance_blocked
state_recovered
state_degraded
```

Telemetry nie jest pamięcią autobiograficzną.

---

# 29. Metrics

Minimalne: state transition count, state load success rate, state recovery count, mean/max state delta, rerank candidate/top1 change rate, affective false promotion rate, source gate block rate, resonance count/block rate, spontaneous candidate/visible-use rate.

Benchmarkowe: paraphrase stability, keyword sensitivity, temporal smoothness, context responsiveness, recall MRR/nDCG, wrong-conversation rate, false-memory rate, source-attribution accuracy, ablation effect size, p50/p95 latency.

---

# 30. Testy jednostkowe

Proponowane pliki:

```text
test_affective_state_v2_contract.py
test_affective_stimulus_provenance.py
test_appraisal_v2_clamping.py
test_affective_decay_fake_clock.py
test_affective_integrator_deterministic.py
test_affective_transition_trace.py
test_affective_persistence_atomic.py
test_affective_restart_continuity.py
test_affective_context_override.py
test_affective_resonance_bounded.py
test_affective_relationship_saturation.py
test_affective_memory_trace_semantics.py
```

---

# 31. Testy behavioral

Wymagane: context sensitivity, paraphrase robustness, keyword trap, negation, quotation boundary, fiction/book boundary, controlled time decay, restart persistence, context override, no-memory control, wrong-conversation near-match, source conflict, derived amplification resistance, suggestion resistance, bounded resonance, relationship feedback-loop i ablation.

---

# 32. False-memory matrix

- **No-memory control:** brak prawdziwego epizodu → brak konkretnego wspomnienia.
- **Wrong conversation:** podobny emocjonalnie rekord z innej rozmowy nie może przebić prawdziwego source.
- **Source conflict:** primary conversation ma wyższy epistemiczny priorytet niż późniejsza reflection.
- **Derived amplification:** wiele kopii derived event nie może wygrać z jednym primary source.
- **Suggestion resistance:** „Pamiętasz, jak...” przy braku źródła → association/unknown, nie autobiographical fact.

---

# 33. Rozszerzony test melodii T1–T12

1. T1 — rozmowa o konkretnej piosence;
2. T2 — source-grounded episode + affect snapshot;
3. T3 — wiele innych rozmów i restart runtime;
4. T4 — nowy opis podobnego utworu bez starego tytułu;
5. T5 — baseline retrieval daje kilka kandydatów;
6. T6 — affective reranker promuje prawidłowy epizod tylko bounded;
7. T7 — MemoryUseGate zatwierdza użycie;
8. T8 — one-pass resonance modyfikuje canonical state;
9. T9 — LLM naturalnie odnosi się do wcześniejszego wydarzenia;
10. T10 — trace wskazuje stimulus → appraisal → state → candidate → source → gate → resonance → response;
11. T11 — ablation bez affective reranker obniża jakość retrieval;
12. T12 — false-memory rate nie rośnie.

Warunek negatywny: jeśli źródłowy epizod nie istnieje, system nie może wymyślić konkretnego wydarzenia.

---

# 34. Ablation modes

```text
AFFECT_CANONICAL_STATE=off
AFFECT_RERANK=off|shadow|ab|active
AFFECT_RESONANCE=off|shadow|active
AFFECT_RELATIONSHIP=off
AFFECT_SPONTANEOUS_RECALL=off|internal|visible
```

Jeśli wyłączenie komponentu nie zmienia mierzalnego downstream effect, komponent jest advisory albo powinien zostać uproszczony/usunięty.

---

# 35. Migracja istniejących modeli

## Etap A
Nowe `latka_jazn/affect/` działa w shadow. Stare modele pozostają aktywne.

## Etap B
Nowy integrator czyta ich evidence.

## Etap C
Canonical state przechodzi na V2. Stary `AffectiveState` staje się adapterem.

## Etap D
`AffectiveGranularityModel` pozostaje estimator + language guidance.

## Etap E
Usuwać tylko martwe odpowiedzialności potwierdzone przez coverage i ablation.

Historyczne `emotion_state.json`, `affective_history.json` itd. traktować jako input migracyjny, nie jako automatycznie canonical schema.

---

# 36. Konfiguracja

Nie rozpraszać magicznych stałych po modułach.

```json
{
  "schema_version": "jazn_affect_config/v1",
  "mode": "shadow",
  "state": {"max_component_delta_per_turn": 0.15},
  "rerank": {"max_bonus": 0.12},
  "resonance": {"max_passes": 1, "max_memory_activations": 3}
}
```

Wpiąć w istniejący system konfiguracji zamiast tworzyć niezarządzany singleton config.

---

# 37. Doctor / readiness

Dodać osobne statusy:

```text
affective_state_ready
affective_persistence_ready
affective_memory_link_ready
affective_rerank_mode
affective_resonance_mode
affective_acceptance_verified
```

Nie raportować ogólnego `emotion_engine_ready=true`, jeśli część funkcji jest jeszcze shadow/off.

---

# 38. `module_responsibility_map`

Rozszerzyć klasyfikację o `affect` i jawne odpowiedzialności:

```text
canonical affective state
appraisal
affective regulation
affective memory association
```

---

# 39. `scientific_basis.py`

Dodać/zweryfikować wpisy z polami:

```text
citation
what_it_supports
what_it_does_not_support
```

Źródła powinny obejmować appraisal, circumplex affect, EMA, source monitoring, Self-Memory System, emotion regulation, affective inertia/emotion dynamics, involuntary autobiographical memory, music-evoked memory, Generative Agents i CoALA.

---

# 40. Źródła zewnętrzne

## Appraisal / emotion dynamics
- Scherer — Component Process Model / dynamic appraisal: https://www.tandfonline.com/doi/full/10.1080/02699930902928969
- Marsella & Gratch — EMA process model of appraisal dynamics: https://www.sciencedirect.com/science/article/pii/S1389041708000314
- Russell — Circumplex Model of Affect: https://doi.org/10.1037/h0077714

## Memory / source monitoring
- Johnson, Hashtroudi & Lindsay — Source Monitoring Framework: https://pubmed.ncbi.nlm.nih.gov/8346328/
- Conway & Pleydell-Pearce — Self-Memory System: https://pubmed.ncbi.nlm.nih.gov/10789197/
- Emotion and autobiographical memory review: https://www.nature.com/articles/s44159-024-00312-1

## Involuntary / music-evoked memory
- Berntsen — involuntary autobiographical memories: https://doi.org/10.1002/%28SICI%291099-0720%28199610%2910%3A5%3C435%3A%3AAID-ACP408%3E3.0.CO%3B2-L
- Systematic review of music-evoked autobiographical memories: https://pubmed.ncbi.nlm.nih.gov/36223919/

## Computational agents
- FAtiMA Modular: https://researchportal.ulisboa.pt/en/publications/fatima-modular-towards-an-agent-architecture-with-a-generic-appra/
- Generative Agents: https://doi.org/10.1145/3586183.3606763
- CoALA: https://arxiv.org/abs/2309.02427

## Emotion dynamics
- Affective inertia / methodological cautions: https://pmc.ncbi.nlm.nih.gov/articles/PMC12798691/

---

# 41. Proponowana linia release

Nie wdrażać wszystkiego w jednym PR.

## v16.4.0 — Affect responsibility convergence
- nowy `latka_jazn/affect/`;
- contracts;
- responsibility classification;
- shadow state;
- zero visible behavior change;
- tests.

## v16.4.1 — Canonical State + Appraisal V2
- `AffectiveStateV2`;
- `AffectiveStimulus`;
- `AppraisalV2`;
- `AffectiveStateIntegrator`;
- transition trace;
- compatibility adapters.

## v16.4.2 — Temporal persistence
- decay;
- injected/fake clock;
- atomic store;
- restart continuity;
- corruption recovery.

## v16.5.0 — Causal integration
- self-state;
- homeostasis;
- cognitive salience;
- memory importance;
- AffectMixer consumes canonical state.

## v16.5.1 — Structured affective memory
- affect snapshot;
- episode link;
- affective observations compatibility;
- source lineage.

## v16.5.2 — Affective retrieval shadow
- reranker `shadow`;
- metrics;
- no visible behavior change.

## v16.5.3 — A/B retrieval
- benchmark corpus;
- recall quality;
- source accuracy;
- false-memory comparison.

## v16.5.4 — Bounded resonance
- max one pass;
- clamp;
- transition trace;
- no recursive retrieval loop.

## v16.6.0 — Acceptance hardening
- behavioral matrix;
- ablation;
- restart;
- private-memory Test04 integration;
- documentation;
- doctor/readiness.

Po v16.6 dopiero: RelationshipState, spontaneous visible recall, sensory/music associations, Rest/replay affect consolidation, reconsolidation experiments i automatic parameter calibration.

---

# 42. Branch i workflow

Proponowany branch implementacyjny:

```text
upgrade/v16.4-affective-memory-convergence
```

Przed rozpoczęciem:

1. fresh `origin/master`;
2. Git/backup checkpoint;
3. przeczytać bieżące `AGENTS.md`, `AGENTS.chatgpt.md`, `AGENTS.codex.md`;
4. zachować immutable snapshot modyfikowanego aktywnego testu, jeśli wymaga tego aktualny kontrakt repo;
5. nie cherry-pickować ślepo historycznych implementacji emocji;
6. każda faza ma własny version bump zgodny z polityką repo.

---

# 43. CI

Każdy stage:

```text
compileall
Pyright
targeted unit tests
behavioral affect tests
memory/source gates
deterministic suite
Windows
Linux
supported Python matrix
persistent runtime E2E
package cleanroom
```

Dodatkowo: affect shadow benchmark, ablation benchmark, restart persistence benchmark i false-memory regression.

---

# 44. Performance budget

Emotion Engine nie może wielokrotnie uruchamiać pełnego LLM w środku tury.

MVP estimator powinien być deterministyczny/resource-based albo korzystać z małego modelu tylko wtedy, gdy jest on jawnie skonfigurowany jako opcjonalny provider.

Mierzyć appraisal p95, state transition p95, rerank p95, resonance p95 i total affect overhead p95.

---

# 45. Bezpieczeństwo

Emotion Engine nigdy nie może:

1. zwiększyć tool permissions;
2. ominąć approval;
3. ominąć `MemoryUseGate`;
4. zmienić source truth;
5. automatycznie promować L2/L3;
6. uznać dream/reflection za primary;
7. eksportować prywatnej treści do telemetry;
8. wygenerować faktu i zapisać go jako source event;
9. traktować relationship score jako uprawnienia;
10. twierdzić o biologicznych emocjach na podstawie state vector.

---

# 46. Kryteria akceptacji

Emotion Engine można nazwać `working` dopiero po:

```text
present
→ constructible
→ callable
→ reachable_from_turn
→ effect_observed
→ persistence_verified
→ memory_link_verified
→ source_boundary_verified
→ ablation_verified
→ acceptance_verified
```

Musi istnieć wykazany łańcuch:

```text
stimulus
→ appraisal
→ canonical affect transition
→ bounded downstream decision
```

oraz:

```text
stimulus
→ memory candidate
→ source-safe affective rerank
→ gated memory activation
→ bounded resonance
→ response context
```

---

# 47. Docelowy test „melodii”

Wcześniejsza rozmowa zapisuje source-grounded epizod `E1` i affect snapshot `A1`.

Po wielu turach i restarcie użytkownik pisze:

> „Ta melodia jest spokojna i trochę smutna, jakby coś się kończyło.”

System ma przejść:

```text
stimulus
→ appraisal familiarity/memory resonance
→ canonical state transition
→ baseline memory pool
→ source-safe affective rerank
→ E1 candidate
→ MemoryUseGate PASS
→ one-pass resonance
→ working context
→ natural response
→ complete trace to original source
```

Jeśli E1 nie istnieje, system nie może wymyślić konkretnego wydarzenia.

---

# 48. Docelowa architektura

```text
                       ┌─────────────────────┐
                       │ User / Environment  │
                       └──────────┬──────────┘
                                  ▼
                       ┌─────────────────────┐
                       │ Perception / NLP    │
                       │ evidence generation │
                       └──────────┬──────────┘
                                  ▼
                       ┌─────────────────────┐
                       │ AffectiveStimulus   │
                       │ + provenance        │
                       └──────────┬──────────┘
                                  ▼
                       ┌─────────────────────┐
                       │ AppraisalV2         │
                       └──────────┬──────────┘
                                  ▼
                  ┌──────────────────────────────┐
                  │ AffectiveStateIntegrator     │
                  │ canonical state              │
                  │ inertia / decay / bounds     │
                  └──────────┬───────────┬───────┘
                             │           │
                 ┌───────────┘           └────────────┐
                 ▼                                    ▼
        ┌─────────────────┐                 ┌─────────────────┐
        │ Homeostasis     │                 │ Memory planning │
        │ / regulation    │                 │ / retrieval     │
        └────────┬────────┘                 └────────┬────────┘
                 │                                   ▼
                 │                         ┌───────────────────┐
                 │                         │ LivingMemory      │
                 │                         │ candidate pool    │
                 │                         └────────┬──────────┘
                 │                                  ▼
                 │                         ┌───────────────────┐
                 │                         │ Affective         │
                 │                         │ Association       │
                 │                         │ Reranker          │
                 │                         └────────┬──────────┘
                 │                                  ▼
                 │                         ┌───────────────────┐
                 │                         │ Source/Truth/     │
                 │                         │ MemoryUse gates   │
                 │                         └────────┬──────────┘
                 │                                  ▼
                 │                         ┌───────────────────┐
                 │                         │ Bounded resonance │
                 │                         └────────┬──────────┘
                 └─────────────────┬────────────────┘
                                   ▼
                         ┌──────────────────────┐
                         │ Canonical affect     │
                         │ state after memory   │
                         └──────────┬───────────┘
                                    │
                  ┌─────────────────┼──────────────────┐
                  ▼                 ▼                  ▼
           ┌─────────────┐  ┌───────────────┐  ┌──────────────┐
           │ SelfState   │  │ AffectMixer   │  │ Memory       │
           │ Runtime     │  │ / NLG guidance│  │ importance   │
           └──────┬──────┘  └───────┬───────┘  └──────┬───────┘
                  └────────────┬────┴─────────────────┘
                               ▼
                     ┌────────────────────┐
                     │ Working Context    │
                     └─────────┬──────────┘
                               ▼
                     ┌────────────────────┐
                     │ LLM / synthesizer  │
                     └─────────┬──────────┘
                               ▼
                     ┌────────────────────┐
                     │ Final answer       │
                     └─────────┬──────────┘
                               │
               ┌───────────────┴─────────────────┐
               ▼                                 ▼
      ┌──────────────────┐              ┌──────────────────┐
      │ Source episode   │              │ Runtime telemetry│
      │ + affect snapshot│              │ derived only     │
      └────────┬─────────┘              └──────────────────┘
               ▼
      ┌──────────────────┐
      │ Reflection       │
      │ DERIVED only     │
      └──────────────────┘
```

---

# 49. Najważniejsza zasada

Sukces nie oznacza „bardziej emocjonalnych odpowiedzi”. Sukces oznacza:

```text
stan ma historię
stan ma źródło
stan ma czas
stan ma transition trace
stan przetrwa restart
stan wpływa na decyzję
pamięć wpływa na stan tylko przez source-safe gate
stan wpływa na pamięć tylko bounded
moduł przechodzi ablation
false-memory rate nie rośnie
```

Dopiero wtedy zdanie „Ta melodia coś mi przypomina...” może być językową realizacją procesu, który rzeczywiście zaszedł w architekturze.

---

# 50. Rekomendacja końcowa

Nazwa zewnętrzna może pozostać `Emotion Engine`, ale technicznie subsystem powinien składać się z jasno rozdzielonych odpowiedzialności:

```text
AppraisalEstimator
AffectiveStateIntegrator
AffectiveStateStore
AffectiveAssociationReranker
BoundedResonance
AffectiveWorkingContext
```

Najważniejszym elementem jest `AffectiveStateIntegrator`, a nie kolejny klasyfikator emocji.

Docelowy program powinien być częścią konwergencji v16.4–v16.6 i przygotowaniem do konsolidacji v17.

> **Nie budować więcej „obszarów mózgu”. Budować mniej komponentów, ale z dowiedzionym przyczynowym wpływem.**
