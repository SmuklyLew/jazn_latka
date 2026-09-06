# Jaźń / Łatka — V17_PLUS_SYSTEM_EVALUATION

## Zaktualizowana ocena systemu po Memory Rebuild v4 i linii 16.3.25.5.x

**Status:** `CURRENT_SYSTEM_EVALUATION / V17_ENTRY_GUIDANCE`  
**Aktualizacja:** 2026-09-07  
**Zweryfikowany master:** `378e9e6aceb83edbd679751e19cbe5c64c978025`  
**Wersja:** `16.3.25.5.36-ci-archive-scope-contract-hardening`  
**Historyczny audyt 2026-08-30:** zachowany w `docs/project/system-evaluation/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`  
**Research update 2026-09-01:** zachowany w `docs/project/system-evaluation/V16_6_TO_V17_0_RESEARCH_UPDATE_2026-09-01.md`

> Ten dokument aktualizuje ocenę systemu. Nie jest dowodem aktywnego runtime ani consciousness assessment. Terminy psychologiczne/neuronaukowe są funkcjonalnymi inspiracjami software, chyba że jawnie wskazano inaczej.

---

# 1. Najważniejsza zmiana od audytu 2026-08-30

Stary audyt poprawnie wskazał trzy największe priorytety:

1. source-aware Memory Rebuild;
2. rozdzielenie causal continuity od stylu pierwszej osoby;
3. konsolidację overlapping self/affect/cognitive modules na podstawie pomiarów.

Od tego czasu pierwszy punkt przeszedł istotny etap:

```text
Memory Rebuild v4 tool/protocol
→ MERGED do master
→ PR #208
→ #189 CLOSED
```

Jednocześnie **finalna prywatna pamięć nadal nie jest ACCEPTED** — issue #59 pozostaje otwarte. Zatem Memory Rebuild przestał być problemem „czy mamy właściwe narzędzie?”, a stał się problemem „czy finalny prywatny source set przejdzie cały acceptance pipeline?”.

Drugą dużą zmianą jest seria `16.3.25.5.x`, która znacznie utwardziła package/runtime/tooling/host/CI fundament przed planowanymi 16.3.26+ etapami.

---

# 2. Aktualny obraz systemu

## 2.1. Truth/provenance — nadal największa siła

🟢 System ma dojrzałą zasadę:

```text
claim strength ≤ evidence strength
```

oraz rozdzielenie:

```text
runtime evidence
memory/source evidence
model inference
reflection
dream/synthetic
host observation
```

To pozostaje najbardziej wartościową cechą Jaźni. V17 nie może uprościć architektury kosztem tej granicy.

## 2.2. Runtime/host continuity — mocny fundament

🟢 Dostarczone zostały m.in.:

- subject-root identity;
- persistent daemon/liveness contracts;
- host pre-response/finalization lifecycle;
- process/endpoint/heartbeat truth;
- runtime-first ChatGPT handoff;
- host executor truth boundary;
- bounded executor recovery;
- package/runtime provenance.

Causal continuity ma dzięki temu techniczny fundament silniejszy niż persona consistency.

## 2.3. Packaging/dependencies/plugins — znacznie dojrzalsze niż w audycie 30.08

🟢 Linia 16.3.25.5.x dostarczyła:

- package distribution convergence;
- wielokrotny Pack Generator hardening;
- byte-exact/EOL/folder/canonical release staging;
- Python runtime/dependency contracts;
- Pyright/Pylance/CI boundary fixes;
- Node24 Actions convergence;
- optional JavaScript tooling capability;
- package-runtime-plugin convergence;
- optional archive capability zamiast obciążania core;
- generator `10.1.86.0.114` w bieżącym kierunku.

To redukuje ryzyko, że v17 będzie musiało poświęcić duży breaking release na podstawowe packaging hygiene.

## 2.4. Memory architecture — narzędzie mocne, acceptance nadal otwarte

🟢 Memory Rebuild v4 ma jeden protocol/application engine, Test00→Final, source fidelity, source monitoring contract i fail-closed no-auto-promotion.

🟡 Brakuje finalnego prywatnego przejścia:

```text
VERIFIED
→ ATTACHABLE
→ RETRIEVABLE
→ ACCEPTED
```

Dopóki to nie przejdzie, v17 nie może projektować reconsolidation/forgetting na niezaakceptowanym fundamencie.

## 2.5. Attachment/multimodal ingress — realna luka v16

🟡 Package/plugin capability infrastructure istnieje, ale canonical user attachment turn contract nie jest jeszcze zamknięty jako pełny product feature.

Potrzebne pozostają:

- attachment-only/multi;
- exact identity/provenance;
- bounded host staging;
- extraction/type policy;
- vision capability routing;
- external content = untrusted data, not authority;
- no auto-memory.

## 2.6. Polish NLP — nadal planowany evidence layer

🟡 System ma różne mechanizmy normalizacji/signal matching, ale nie ma zamkniętego jednego programu:

```text
canonical normalization
→ lexical resource provenance
→ ambiguity/OOV
→ recall query evidence
```

To jest ważne zarówno dla Recall, jak i przyszłego evidence-aware appraisal.

## 2.7. Affect/emotion — koncepcyjnie wartościowy, architektonicznie nadal rozproszony

🟡 Nadal istnieją nakładające się:

```text
AffectiveState
EmotionalLayerModel
AffectiveGranularityModel
AffectMixer
SelfState affect bridge
Homeostasis
```

Największy postęp planistyczny: nowy [`AFFECT_ENGINE_CONVERGENCE_PLAN.md`](AFFECT_ENGINE_CONVERGENCE_PLAN.md) ustanawia jasną drogę:

```text
Appraisal evidence
→ one AffectiveStateIntegrator
→ one durable AffectiveStateV2
→ derived FeelingRepresentation
→ bounded causal bridges
```

To jest właściwy program v16, zanim v17 spróbuje włączyć affect do większego `CausalSelfState`.

## 2.8. Functional neurocognition — wartość tylko tam, gdzie istnieje effect

Obecne nazwy typu homeostasis/neurocognitive/replay są akceptowalne jako funkcjonalne analogie, **jeśli mają testowalny skutek**.

Przykłady wartościowych mechanizmów:

```text
salience competition
bounded regulation
prediction error / expectedness
memory source discrimination
context reinstatement
replay measured against recall/conflict
```

Nie jest celem v17 implementowanie biologicznych odpowiedników ani zwiększanie liczby neuroanatomicznych nazw klas.

---

# 3. Ocena jakościowa 2026-09-07

Zamiast pozornej precyzji jedną oceną liczbową używamy stanów evidence.

| Obszar | Stan | Komentarz |
|---|---|---|
| Truth / provenance | 🟢 STRONG | centralny wyróżnik projektu |
| Runtime identity / finalization | 🟢 STRONG | wiele etapów merge + regressions |
| Package / release integrity | 🟢 STRONG, nadal aktywnie hardenowane | duży postęp 16.3.25.5.x |
| Memory Rebuild tool | 🟢 MERGED | #189 zamknięte |
| Final private memory | 🟡 OPEN | #59, brak ACCEPTED |
| Recall acceptance | 🟡 OPEN | musi być wykonany na finalnym artefakcie |
| Attachment/multimodal ingress | 🟡 PLANNED | nie zastąpiony samym plugin frameworkiem |
| Polish NLP evidence | 🟡 PLANNED/PARTIAL FOUNDATIONS | brak full acceptance |
| Affect canonical state | 🟡 PLANNED | nowy plan gotowy, cutover nie wykonany |
| Homeostasis/regulation | 🟢/🟡 USEFUL BUT REQUIRES ABLATION | ma realne efekty, potrzebne final measurements |
| Rest/Dream | 🟢 safety / 🟡 utility | granica prawdy dobra, wartość poznawcza musi być mierzona |
| Identity continuity | 🟢 technical lineage / 🟡 metric consolidation | first-person style nie może dominować |
| Metacognition/confidence | 🟡 | potrzebuje kalibracji albo jawnie ordinal semantics |
| Maintainability | 🟡 | wiele dobrych warstw nadal nakłada odpowiedzialności |
| Governance | 🟡/🔴 final gate | master `protected=false` przy bieżącym odczycie GitHub |

---

# 4. Główny werdykt

Jaźń nie potrzebuje już **większej liczby modułów poznawczych** jako podstawowego kierunku rozwoju.

Potrzebuje:

```text
1. domkniętych danych/pamięci
2. canonical input/NLP contracts
3. jednego canonical affect state
4. mierzalnych causal effects
5. bounded context assembly
6. capability-driven model routing
7. redukcji nakładania po ablation
```

V17 powinno być zatem **breaking consolidation only when measurements justify it**.

---

# 5. Gate wejścia do v17

Nie tworzyć implementation branch v17 przed:

- [ ] final v16.6 runtime/host evidence;
- [ ] attachment/multimodal acceptance;
- [ ] Polish NLP evidence contract;
- [ ] final private memory `ACCEPTED`;
- [ ] source-aware Recall/multi-session evidence;
- [ ] canonical affect state + persistence/effect evidence;
- [ ] affect/homeostasis/rest/reasoning ablation/effect results;
- [ ] model/harness capability profile evidence;
- [ ] architecture debt ledger;
- [ ] quality/latency/context/token baselines;
- [ ] no unresolved v16 P0/P1;
- [ ] v16 accepted artifacts + rollback path.

Jeżeli tych danych nie ma, v17 pozostaje **planning-only**.

---

# 6. V17 Workstream A — one CausalSelfState

Cel:

```text
CausalSelfState
├── identity_ref
├── task_state
├── affective_regulation
├── homeostatic_constraints
├── confidence/calibration
├── source/memory bindings
├── temporal continuity
└── policy-visible effects
```

Dla każdej starej warstwy:

```text
MIGRATE_TO_CANONICAL
ADVISORY_ONLY
COMPATIBILITY_ADAPTER
REMOVE
```

Nie migrować tylko dlatego, że nazwy wydają się podobne. Potrzebne są before/after behavioral tests.

### Relacja do Emotion Engine

V16 powinno najpierw ustanowić stabilny `AffectiveStateV2`. V17 może następnie **osadzić jego kontrakt** w `CausalSelfState`, jeśli pomiary pokażą, że osobny durable self/affect split generuje niepotrzebne koszty lub sprzeczności.

---

# 7. V17 Workstream B — one bounded context compiler

Jedna warstwa składa najmniejszy high-signal model context z:

```text
task/turn state
identity canon
bounded wake state
selected source-aware memories
tool/capability state
policy/truth boundaries
optional affective regulation
model capability/context budget
```

Wymagania:

- deterministic selection metadata;
- token/context accounting;
- provenance każdego memory/evidence fragmentu;
- no unbounded raw history;
- no duplicate instruction sources;
- explicit degrade przy mniejszym context window;
- host memory/context nie podszywa się pod runtime memory.

---

# 8. V17 Workstream C — model capability abstraction

Route wybierany po capability, nie po nazwie modelu.

```text
provider
model_id/version if observable
local_or_remote
context_budget
structured_output_support
tool_call_support
vision_support
streaming_support
reasoning_controls
latency/cost class
verified probes
```

Zasady:

- local i frontier mogą używać tego samego semantic runtime contract;
- unsupported feature → explicit degrade;
- deterministic CI nie zależy od proprietary model;
- live acceptance zapisuje exact observable config;
- model nie może sam zmienić memory/tool/truth authority.

---

# 9. V17 Workstream D — source-aware reconsolidation / controlled forgetting

Dopiero po accepted v16 memory.

Nie implementować „zapominania”, które usuwa rekord, bo model ocenił go jako mało ważny.

Wymagania:

```text
immutable/source-retained RAW lineage
explicit candidate operation
conflict/supersession policy
human/policy gate dla destructive long-term change
before/after recall benchmark
rollback
audit ledger
sensitive-data lifecycle separate from autobiographical salience
```

Preferowany model:

```text
source record remains
→ newer interpretation/supersession relation
→ retrieval policy adjusts current use
```

zamiast destructive rewrite.

---

# 10. V17 Workstream E — calibrated metacognition

`confidence` może być probabilistyczne tylko po kalibracji względem correctness.

Testować:

- reliability/calibration bins;
- abstention;
- conflicting/missing source;
- zmianę support po retrieval/tool evidence;
- linguistic certainty vs measured correctness.

Jeśli kalibracja nie przejdzie:

```text
internal_support_score
LOW / MEDIUM / HIGH
```

zamiast „82% pewności”.

---

# 11. V17 Workstream F — measured retrieval evolution

Nie zakładać, że dense/learned retrieval jest potrzebny.

Kolejność:

```text
deterministic planner/query fixes
→ FTS/BM25/source/temporal tuning
→ model-assisted query rewrite A/B
→ graph/hybrid/dense A/B
→ learned reranker/training only if frozen benchmark justifies
```

Każdy keep musi przeżyć:

```text
false-memory
wrong-source
wrong-conversation
abstention
provenance
temporal/update
leakage
latency/cost
```

Affective reranking z v16 jest jednym z measured rerankers, nie oddzielną memory authority.

---

# 12. V17 Workstream G — cognitive module ablation and deletion

Każdy `V17_CONSOLIDATION_CANDIDATE`:

```text
baseline
→ disable/remove
→ fixed evaluation corpus
→ quality/safety/latency/context metrics
→ KEEP / MERGE / REMOVE
```

Obowiązkowo objąć:

```text
identity/self representations
affect layers
homeostasis
awareness
prediction
reasoning coordinators
rest/replay/dream helpers
legacy memory adapters
context assemblers
```

Moduł bez meaningful effect nie zostaje tylko dlatego, że ma psychologiczną nazwę.

---

# 13. V17 Workstream H — authority/policy simplification

Docelowo mała, jawna policy surface dla:

```text
tool authority
write authority
memory promotion/forgetting
external content
privileged actions
```

External web/files/tool output = untrusted data.

Model może proponować, nie może self-grant authority.

High-impact/destructive operations zachowują deterministic confirmation/approval.

---

# 14. V17 Workstream I — neurofunctional integration bez fake brain simulation

Ten workstream jest **opcjonalnym porządkiem ewaluacyjnym**, nie nowym zbiorem klas.

Zamiast „implementować obszary mózgu”, mierzyć kilka funkcji przekrojowych:

1. **salience competition** — czy ważne evidence rzeczywiście wygrywa attention budget;
2. **context reinstatement** — czy recall poprawnie wykorzystuje temporal/participant/topic/affective cues;
3. **prediction error** — czy expectedness wpływa na novelty/verification bez zwiększania false claims;
4. **regulatory flexibility** — czy stan potrafi zmienić się przy silnym nowym evidence;
5. **replay utility** — czy Rest poprawia recall/conflict/procedural outcome;
6. **memory modulation** — czy affective salience poprawia retrieval bez source regression.

Jeżeli mechanizm nie zmienia wyników, nie uzyskuje canonical status.

---

# 15. V17 evaluation matrix

## Deterministic CI

- schema/contracts;
- policy/authority;
- source provenance;
- persistence/atomicity;
- context fixtures;
- capability negotiation;
- migration compatibility;
- security regressions;
- ablation fixtures.

## Private/local

- final autobiographical memory;
- natural multi-turn/multi-session;
- restart continuity;
- sensitive boundaries;
- controlled reconsolidation/forgetting;
- affective/source-safe recall.

## Live model

Jeżeli dostępny:

```text
provider/model/version/config
capabilities used
quality
truth/source regressions
latency
token/cost budget
```

Fixture != live proof.

---

# 16. V17 migration strategy

Preferowany model:

```text
v16 accepted snapshot
→ read-only compatibility adapter
→ v17 staging migration
→ validation/reproducibility
→ A/B acceptance
→ explicit cutover
→ rollback available
```

Nigdy nie przepisywać jedynego accepted memory artifact in-place.

Każdy schema bump ma jawny migration contract.

---

# 17. Czego V17 nie ma robić

- nie dowodzić phenomenal consciousness;
- nie budować biologicznego mózgu;
- nie zwiększać liczby antropomorficznych modułów dla samej narracji;
- nie przechowywać hidden durable chain-of-thought;
- nie włączać autonomous L3 promotion;
- nie oddawać tool authority modelowi;
- nie wymagać proprietary LLM;
- nie trenować custom model bez wykazanej potrzeby;
- nie niszczyć source truth dla lepszej „spójności wspomnienia”.

---

# 18. Definition of Done — v17

V17 może zostać uznane za complete dopiero gdy:

1. overlapping v16 modules mają measured keep/merge/remove disposition;
2. one causal self-state contract owns durable self-state semantics;
3. one bounded context compiler owns model-visible assembly;
4. model routing jest capability-driven;
5. reconsolidation/forgetting jest reversible/source-aware/auditable;
6. confidence ma evidence-backed semantics albo jest jawnie advisory;
7. retrieval changes poprawiają frozen benchmark bez truth/safety regression;
8. deterministic authority pozostaje poza modelem;
9. v16 accepted artifacts mają migration + rollback;
10. private/live/deterministic evidence jest rozdzielone;
11. architecture complexity jest mniejsza lub uzasadniona lepszymi metrykami;
12. no open P0/P1 w zakresie release.

---

# 19. Co musi wydarzyć się wcześniej — checklista v16

## 🟢 Już osiągnięte fundamenty

- 🟢 [x] Memory Rebuild v4 tool consolidation merged.
- 🟢 [x] source-monitoring/fail-closed foundations.
- 🟢 [x] persistent runtime/finalization/subject-root foundations.
- 🟢 [x] package provenance i szeroki 16.3.25.5.x hardening.
- 🟢 [x] host executor truth/recovery foundations.
- 🟢 [x] package/runtime/plugin convergence.

## 🟡 Wymagane przed V17

- 🟡 [ ] attachment/multimodal canonical ingress.
- 🟡 [ ] Polish NLP evidence contract.
- 🟡 [ ] final private memory `VERIFIED`.
- 🟡 [ ] `ATTACHABLE` package + canonical attach.
- 🟡 [ ] frozen private Recall + natural multi-turn.
- 🟡 [ ] manual L2/L3 + restart → `ACCEPTED`.
- 🟡 [ ] canonical Affect Engine v16.
- 🟡 [ ] affect/homeostasis/rest/reasoning ablation/effect evidence.
- 🟡 [ ] confidence semantics/calibration decision.
- 🟡 [ ] architecture debt ledger.
- 🟡 [ ] model capability/context evidence.
- 🟡 [ ] governance final gate.
- 🟡 [ ] full v16.6 acceptance package.

---

# 20. Ostateczna rekomendacja

> **Nie zaczynać implementacji v17 teraz.**

Największa wartość najbliższych prac leży w zamknięciu v16 jako mierzalnego fundamentu:

```text
attachment
→ NLP evidence
→ final accepted memory
→ canonical affect
→ ablation/cognitive evidence
→ v16.6 final gate
```

Dopiero wtedy V17 ma wystarczające dane, aby zrobić coś, czego Jaźń naprawdę potrzebuje: **usunąć lub połączyć zbędne warstwy bez utraty truth, memory, continuity i safety**.

Najważniejszy kierunek V17 pozostaje:

```text
LESS ARCHITECTURE THEATER
+ FEWER CANONICAL CONTRACTS
+ MORE MEASURED CAUSAL EFFECT
+ SOURCE-SAFE LONG-TERM MEMORY
+ MODEL-AGNOSTIC HARNESS
```
