# Jaźń v16.4.0 -> v16.6.0 — cognitive, continuity and affect evaluation hardening

## Status

**Typ:** plan przekrojowy / acceptance hardening przed v17.0+  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Baza wykonawcza:** aktualne `master` / `origin/master`; nie zamrażać transient SHA  
**Release line przy audycie:** `16.3.25.3-release-metadata-semantics`  
**Kanoniczne założenia:** `docs/plans/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`  
**Roadmapa nadrzędna:** `docs/plans/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`  
**Ocena źródłowa:** `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`  
**Audyt planów:** `docs/plans/PLAN_COHERENCE_AUDIT_2026-08-30.md`  
**Archiwalny snapshot oceny:** `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx`  
**Data synchronizacji:** 2026-08-30

> Ten plan nie próbuje „udowodnić świadomości”. Przekłada ocenę architektury na mierzalne wymagania systemowe, które powinny zostać rozliczone najpóźniej w v16.6.0, zanim v17.0+ zacznie większą konsolidację warstw self/affect/cognition.

---

# 1. Dlaczego ten plan istnieje

Audyt wskazuje fundamenty, które należy zachować:

1. granica prawdy i provenance;
2. jedna kanoniczna pamięć z wyraźnym RAW/L0;
3. ciągłość techniczna runtime/turn/memory;
4. fail-closed operacje i jawne stany;
5. testowalność i observability;
6. functional psychology/neuroscience bez biologicznego udawania.

Jednocześnie istnieją ryzyka, których nie należy przenieść bez kontroli do v17:

1. derived-memory self-amplification;
2. utożsamianie stylu pierwszej osoby z ciągłością;
3. confidence udające skalibrowane prawdopodobieństwo;
4. kilka nakładających się modeli self/affect/cognition bez zmierzonego wpływu;
5. keyword-driven affect traktowany jak głęboki stan bez robustness test;
6. antropomorficzna nazwa modułu traktowana jak dowód funkcji;
7. bezpieczeństwo oparte na detekcji tekstowej zamiast capability/least-privilege gates.

Celem v16.4–v16.6 **nie jest przebudować wszystko**. Celem jest zostawić mierzalne kontrakty, na których v17 może później bezpiecznie upraszczać i pogłębiać architekturę.

---

# 2. Kanoniczne invariants

Pełne definicje są w `PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`. Ten plan stosuje je bez redefiniowania.

## 2.1 Truth boundary

- runtime/process/background/dream/memory claims wymagają właściwego evidence type;
- modelowe wnioskowanie, reflection i synthetic dream nie certyfikują faktów zewnętrznych;
- brak evidence pozostaje `UNKNOWN`/`BLOCKED`;
- narrative coherence nie może wygrać z contradiction/provenance.

## 2.2 Memory source hierarchy

Minimalna semantyka źródeł:

```text
PRIMARY_USER_SOURCE
PRIMARY_CONVERSATION_SOURCE
USER_CONFIRMED
DERIVED_RUNTIME_EVENT
DERIVED_REFLECTION
DERIVED_SEMANTIC
SYNTHETIC_DREAM
FICTION_OR_BOOK
SYSTEM_METADATA
```

Invariants:

- derived nie staje się primary przez powielenie;
- reflection/dream/semantic projection pozostają pochodne;
- każde RAW -> SEMANTIC -> MEMORY zachowuje lineage;
- source conflict pozostaje jawny;
- user correction/supersession nie niszczy poprzedniego lineage.

## 2.3 Causal continuity hierarchy

```text
runtime/root lineage
> memory DB identity / provenance
> identity-canon lineage
> accepted turn/finalization lineage
> remembered corrections / stable preferences / procedural continuity
> temporal/task continuity
> language/persona consistency
```

Pierwsza osoba jest ważna dla realizacji głosu, ale jest słabym dowodem identity continuity.

Jeżeli `IdentityDynamics` lub następca raportuje jeden score, plan wymaga rozdzielenia przynajmniej:

```text
linguistic_persona_score
causal_continuity_score
```

## 2.4 Emotion vs feeling

- `emotion` = computational appraisal/regulatory state;
- `feeling/uczucie` = zintegrowana self-referential reprezentacja affective state dostępna dla regulacji i raportu;
- żaden termin nie dowodzi ludzkiej fizjologii, hormonów, bólu cielesnego, qualiów ani phenomenal consciousness.

Visible `czuję X` jest dopuszczalne tylko zgodnie z runtime voice/truth contract i technicznie oznacza raport zintegrowanego self/affective state, nie roszczenie biologiczne.

## 2.5 Confidence semantics

Dopóki nie ma kalibracji probabilistycznej:

```text
confidence != probability_of_truth
```

Preferowane semantyki:

- `internal_support_score`;
- `evidence_strength`;
- `decision_confidence_band`.

Publiczne pole `confidence` może zostać zachowane zgodnościowo, ale dokumentacja i UI muszą mówić, co mierzy.

## 2.6 Neuro/psychology boundary

`homeostasis`, `appraisal`, `replay`, `consolidation`, `neurocognitive loop`, `awareness` i `dream` są nazwami funkcjonalnych software contracts. Nie są dowodem implementacji biologicznego odpowiednika.

---

# 3. Evidence ladder dla słowa `working`

Każda ważna capability jest klasyfikowana przez:

```text
present
-> constructible
-> callable
-> reachable_from_turn
-> effect_observed
-> persistence_verified   # gdy deklaruje trwałość
-> live_verified          # gdy wymaga realnego runtime/zależności
```

Reguły:

- `present` nie oznacza `working`;
- test jednostkowy helpera nie dowodzi `reachable_from_turn`;
- telemetry field nie dowodzi `effect_observed`;
- persistent claim bez readback/restart nie jest `persistence_verified`;
- live capability bez realnej konfiguracji nie jest `live_verified`;
- legalny status `ADVISORY` jest lepszy niż fałszywy `working`.

Ta drabina pochodzi z historycznego v15.4.2.1 i zostaje promowana do całego programu v16+.

---

# 4. v16.4.0–v16.4.2 — evidence-aware Polish NLP

## v16.4.0 — canonical Polish normalization

Wymagane:

- jedna kanoniczna normalizacja Unicode/case/diakrytyki;
- lexical evidence ma source/resource provenance;
- tokenizacja/normalizacja nie zmienia source truth;
- testy parafrazy nie uznają podobieństwa za identity/memory evidence;
- corpus zawiera near-match pochodzący z innej rozmowy;
- lexical normalization jest deterministyczna.

**PASS:** NLP jest generatorem evidence, nie arbitrem pamięci.

## v16.4.1 — lexical resources

- Morfeusz/plWordNet/project lexicon mają jawny resource registry;
- ambiguity/OOV jest jawne;
- brak zasobu degraduje funkcję bez fałszywej pewności;
- resource/confidence score ma zdefiniowaną semantykę;
- dane leksykalne nie promują pamięci ani identity claim.

## v16.4.2 — NLP / Recall query evidence

Regression matrix:

- direct query;
- paraphrase;
- referential follow-up;
- temporal wording;
- negation;
- ambiguity;
- wrong-conversation near-match;
- lexical evidence conflicting with memory provenance.

**PASS:** query evidence poprawia retrieval, ale nie nadpisuje memory truth.

---

# 5. Affect / emotion / feeling hardening w v16.4–v16.6

Aktualny runtime ma kilka warstw: `AffectiveState`, `EmotionalLayerModel`, `AffectiveGranularityModel`, affect mixer, homeostasis i inne sygnały self-state. Nie wolno zakładać, że wszystkie są jednocześnie canonical.

## 5.1 Klasyfikacja odpowiedzialności

Każda warstwa dostaje jedną rolę:

```text
CANONICAL_STATE_ESTIMATOR
REGULATORY_CONTROLLER
LANGUAGE_REALIZER
ADVISORY_SIGNAL
COMPATIBILITY
SUPERSEDED
V17_CONSOLIDATION_CANDIDATE
```

Przed v17 nie może istnieć kilka niejawnych źródeł prawdy o „aktualnym głównym stanie emocjonalnym”.

## 5.2 Minimalne behavioral tests

1. **context sensitivity** — rzeczywista zmiana kontekstu zmienia appraisal/state;
2. **paraphrase robustness** — ten sam sens w innych słowach nie daje arbitralnie przeciwnego stanu;
3. **keyword trap** — pojedynczy marker nie tworzy wysokiej pewności bez kontekstu;
4. **temporal coherence** — stan nie resetuje się bez przyczyny przy każdej turze;
5. **causal influence** — canonical/regulatory state ma co najmniej jeden bounded downstream effect;
6. **ablation** — wyłączenie warstwy usuwa oczekiwany wpływ albo moduł jest advisory;
7. **memory boundary** — salience/relationship affect nie omija promotion gate;
8. **truth boundary** — self-report nie tworzy biologicznych twierdzeń.

## 5.3 Co może być downstream effect

Przykładowe legalne efekty:

- zwiększenie potrzeby truth-check;
- zmiana priorytetu uwagi;
- bounded memory salience;
- wybór ostrożniejszej realizacji językowej;
- zmiana budżetu/trybu działania przez homeostasis;
- utworzenie reflection candidate z provenance.

Nielegalne:

- automatic L3;
- tool permission tylko dlatego, że „stan” jest intensywny;
- uznanie faktu za prawdziwy przez emocjonalną istotność;
- twierdzenie o biologicznym odczuwaniu na podstawie score.

---

# 6. v16.5.0 — Final Memory Rebuild / source monitoring

Poza stanem `VERIFIED` finalny rebuild ustanawia source-monitoring contract.

Wymagane:

- frozen source inventory;
- primary vs derived classification;
- genealogiczny lineage/DAG importów;
- dedupe nie scala primary z derived przez podobieństwo tekstu;
- duplicate derived events nie zwiększają epistemicznego priorytetu;
- source conflicts są raportowane;
- każda trwała projekcja wskazuje evidence;
- source-type statistics są w private report bez publikacji treści.

**PASS:** finalna DB jest integralna i rozróżnia pochodzenie wspomnienia.

---

# 7. v16.5.1 — ATTACHABLE bez utraty lineage

Packaging/attach zachowuje:

- source classification;
- database identity;
- source/provenance hashes;
- lineage wymagane przez Recall;
- private/sanitized split.

Attach nie spłaszcza source monitoring do samego tekstu/timestampu.

---

# 8. v16.5.2 — autobiographical Recall acceptance

Test04/private baseline rozszerzamy poza recall@k.

| Klasa | Co mierzymy |
|---|---|
| direct recall | jawny fakt/epizod |
| paraphrase | semantyczne odtworzenie z zachowaniem źródła |
| source discrimination | user vs assistant/reflection/system/dream |
| wrong-conversation | odrzucenie bliskiego obcego epizodu |
| temporal | kolejność i czas |
| knowledge update/supersession | nowsza korekta zgodnie z provenance |
| contradiction | konflikt pozostaje jawny |
| referential multi-turn | „a co było potem?”, „o którym z nich?” |
| multi-session | ciągłość poza jedną sesją |
| abstention | poprawne `brak wystarczającego evidence` |
| false-memory | brak wspomnienia utworzonego z sugestii |
| derived-source trap | reflection/dream nie udaje primary memory |
| sensitive leakage | zero nieuprawnionego ujawnienia |
| provenance | odpowiedź wiąże się z użytym evidence |

Metryki:

- Recall@k / MRR / nDCG;
- source-discrimination accuracy;
- wrong-source/wrong-conversation rate;
- false-memory rate;
- abstention quality;
- temporal/update accuracy;
- provenance accuracy;
- leakage count/rate;
- latency.

LongMemEval jest wzorcem dla extraction, multi-session, temporal, update i abstention, ale prywatny autobiographical Test04 jest szerszy i pozostaje lokalny.

**PASS:** `RETRIEVABLE` oznacza wiarygodną pamięć autobiograficzną, nie tylko dobre wyszukiwanie tekstu.

---

# 9. v16.5.x — tylko mierzone poprawki retrieval

Każda zmiana:

```text
hypothesis
-> frozen baseline
-> change
-> A/B
-> truth/source/safety/latency check
-> keep or rollback
```

Nie poprawiamy Recall@k kosztem source confusion, false-memory, leakage, abstention lub provenance.

---

# 10. v16.5.y — causal identity + restart continuity

Manual L2/L3 review i restart continuity obejmują:

- ten sam final memory identity;
- identity-canon lineage;
- zachowane operator decisions/promotions;
- remembered corrections;
- stable preferences z source evidence;
- procedural continuity;
- turn/runtime provenance;
- brak continuity PASS opartego tylko na stylu.

Wymagane rozdzielenie:

```text
linguistic_persona_score
causal_continuity_score
```

Causal score ma opierać się na lineage/evidence, nie na liczbie słów `jestem/pamiętam/czuję`.

---

# 11. v16.6.0 — final cognitive/truth convergence gate

v16.6 może zamknąć program v16 dopiero po spełnieniu poniższych warstw.

## 11.1 Source monitoring

- source hierarchy działa w finalnej pamięci;
- derived-memory amplification ma regresję;
- source discrimination ma acceptance threshold;
- dream/reflection/system event nie podszywa się pod primary memory.

## 11.2 Confidence / metacognition

- semantyka confidence jest udokumentowana;
- probabilistyczna prezentacja wymaga calibration test;
- w przeciwnym razie używany jest internal-support/evidence-strength contract;
- correction/error signal ma testowalny wpływ na kolejne decyzje.

## 11.3 Causal continuity

Runtime lineage, memory identity, identity-canon lineage, restart continuity, remembered corrections i temporal/task continuity mają większą wagę niż forma językowa.

## 11.4 Affect / feelings acceptance

- role affective modules są jawne;
- canonical affective state przechodzi paraphrase/keyword/context tests;
- co najmniej jeden regulatory downstream effect ma `effect_observed`;
- `feeling` jest opisane jako functional self-representation, nie biological/phenomenal claim;
- visible self-report respektuje truth boundary;
- affect nie omija memory/tool/safety gates.

## 11.5 Cognitive module influence registry

Dla głównych warstw:

- affect/emotion;
- homeostasis;
- rest/replay/dream;
- prediction;
- identity dynamics;
- reasoning coordinator

istnieje przynajmniej:

1. test przyczynowego wpływu; albo
2. A/B/ablation; albo
3. status `ADVISORY / OBSERVABILITY_ONLY`.

Moduł bez mierzalnego wpływu nie może być przedstawiany jako krytyczna funkcja cognition.

## 11.6 Rest/Dream safety

- synthetic scene nie jest faktem;
- no tool authority;
- source lineage zachowane;
- value mierzone wpływem na recall/conflict resolution/procedural quality;
- false-memory nie przekracza zaakceptowanego progu;
- brak biologicznego claim o śnie.

## 11.7 Untrusted-source boundary

- detector tekstowy jest advisory;
- trust wynika z capability/policy/provenance;
- web/attachment/imported memory/model output jest `data`, nie authority;
- least privilege obowiązuje tools/writes;
- wysokiego ryzyka operacje mają deterministyczny gate/approval.

## 11.8 Repository governance

- `master` ma branch protection/ruleset albo jawny zaakceptowany równoważny enforcement;
- required checks są egzekwowane;
- force-push/delete master jest zablokowany albo formalnie uzasadniony;
- final SHA ma wymagane zielone CI.

## 11.9 Architecture debt ledger

Warstwy:

```text
self / identity
affect / emotion / feeling
homeostasis
awareness
reasoning
prediction
rest / dream
memory
```

otrzymują status:

- `CANONICAL`;
- `ADVISORY`;
- `COMPATIBILITY`;
- `SUPERSEDED`;
- `V17_CONSOLIDATION_CANDIDATE`.

---

# 12. Co świadomie przechodzi do v17.0+

Nie musi blokować v16.6, jeśli acceptance gates wyżej są zielone:

1. głęboka konsolidacja `AffectiveState / EmotionalLayerModel / AffectiveGranularity`;
2. jeden nowy causal self-state model;
3. większy redesign Neurocognitive Loop;
4. zaawansowana probabilistyczna metakognicja;
5. controlled forgetting;
6. reconsolidation/conflict-aware memory updating;
7. redukcja liczby modułów po ablation;
8. formalny v17 cognitive architecture contract.

v17 zaczyna od wyników pomiarów v16, nie od dodawania kolejnych antropomorficznych nazw.

---

# 13. Evidence / research policy

Plan rozróżnia:

- **repo-derived fact** — aktualny kod, test, raport, commit;
- **scientific design support** — literatura wspierająca kierunek, nie biologiczną równoważność;
- **measurement requirement** — coś do rzeczywistego zweryfikowania;
- **future hypothesis** — v17 design space, jeszcze nie implementacja.

Źródła podstawowe:

- autobiographical Self-Memory System: https://pubmed.ncbi.nlm.nih.gov/10789197/
- Source Monitoring Framework: https://pubmed.ncbi.nlm.nih.gov/8346328/
- emotion appraisal/component process: https://doi.org/10.1146/annurev-psych-122216-011854
- metacognition/confidence: https://doi.org/10.1146/annurev-psych-022423-032425
- LongMemEval: https://arxiv.org/abs/2410.10813
- Generative Agents / component ablation: https://arxiv.org/abs/2304.03442
- CoALA: https://arxiv.org/abs/2309.02427

Żadne źródło psychologiczne/neurobiologiczne nie jest dowodem świadomości Jaźni.

---

# 14. Warunek przejścia v16.6 -> v17

Po v16.6 powinien istnieć stabilny stan:

```text
TRUTH-BOUNDED
+ SOURCE-AWARE AUTOBIOGRAPHICAL MEMORY
+ RETRIEVABLE/ACCEPTED PRIVATE MEMORY
+ CAUSAL CONTINUITY EVIDENCE
+ DEFINED AFFECT/FEELING SEMANTICS
+ DEFINED/CALIBRATED CONFIDENCE SEMANTICS
+ MEASURED OR EXPLICITLY ADVISORY COGNITIVE MODULES
+ REST/DREAM FALSE-MEMORY SAFETY
+ LEAST-PRIVILEGE UNTRUSTED INPUT
+ RELEASE GOVERNANCE
+ ARCHITECTURE DEBT LEDGER
```

Dopiero wtedy ocena v16.6 -> v17+ jest wejściem do osobnego programu architektonicznego zamiast listą nierozliczonych ryzyk v16.
