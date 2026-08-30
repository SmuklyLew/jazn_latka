# Jaźń v16.4.0 -> v16.6.0 — cognitive evaluation hardening plan

## Status

**Typ:** plan przekrojowy / acceptance hardening przed v17.0+  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Baza planu:** `master @ a8f5c0cc0c5a5a2add8714d29e56659e9d5a6c8e`  
**Wersja bazowa:** `16.3.25.3-release-metadata-semantics`  
**Roadmapa nadrzędna:** `docs/plans/JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md`  
**Ocena źródłowa:** `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`  
**Archiwalny snapshot DOCX:** `docs/plans/JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx`  
**Data synchronizacji:** 2026-08-30

> Ten plan nie próbuje „udowodnić świadomości”. Przekłada ocenę architektury na mierzalne wymagania systemowe, które powinny zostać domknięte najpóźniej w v16.6.0, zanim v17.0+ zacznie większą przebudowę warstw self/affect/cognition.

---

## 1. Dlaczego ten plan istnieje

Audyt v16.6 -> v17+ wskazał pięć mocnych fundamentów, które należy zachować:

1. granica prawdy i provenance;
2. jedna kanoniczna pamięć z wyraźnym RAW/L0;
3. ciągłość techniczna runtime/turn/memory;
4. fail-closed operacje i jawne stany;
5. testowalność oraz observability.

Jednocześnie wskazał sześć ryzyk, których nie należy przenosić bez kontroli do v17:

1. derived-memory self-amplification;
2. utożsamianie stylu pierwszej osoby z ciągłością tożsamości;
3. confidence udające skalibrowane prawdopodobieństwo;
4. wiele częściowo nakładających się modeli self/affect/cognition bez zmierzonego wpływu;
5. nadmierne traktowanie psychologicznych/neurobiologicznych analogii jako implementacji;
6. bezpieczeństwo oparte zbyt mocno na detekcji tekstowej zamiast capability/least-privilege gates.

Celem v16.4–v16.6 nie jest przebudować wszystko. Celem jest ustanowić **mierzalne kontrakty**, na których v17 może później bezpiecznie upraszczać i pogłębiać architekturę.

---

## 2. Twarde invariants do zachowania przez całą linię

### 2.1 Truth boundary

- runtime/process/background/dream/memory claims wymagają właściwego evidence type;
- modelowe wnioskowanie, reflection i synthetic dream nie mogą certyfikować faktów zewnętrznych;
- brak dowodu pozostaje `UNKNOWN`/`BLOCKED`, a nie „prawdopodobnie PASS”.

### 2.2 Memory source hierarchy

Każdy trwały lub recall-eligible rekord powinien dać się przypisać do jawnej klasy źródła:

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

Nazwy mogą zostać dopasowane do istniejącego modelu repo, ale semantyka musi pozostać jawna.

Invariants:

- źródło pochodne nie może stać się „bardziej prawdziwe” przez wielokrotne powielenie;
- konflikt primary source vs derived reflection rozstrzyga się na korzyść source evidence albo jawnego UNKNOWN;
- dream/reflection/semantic projection pozostają pochodne;
- liczba kopii derived eventu nie zwiększa epistemicznego priorytetu;
- każde przekształcenie RAW -> SEMANTIC -> MEMORY zachowuje lineage.

### 2.3 Continuity evidence hierarchy

Dowody ciągłości mają priorytet:

```text
runtime/root lineage
-> memory DB identity / provenance
-> identity-canon lineage
-> remembered corrections / stable preferences / procedural continuity
-> temporal/task continuity
-> language/persona consistency
```

Styl pierwszej osoby jest sygnałem pomocniczym, nie głównym dowodem ciągłości.

### 2.4 Confidence semantics

Dopóki system nie ma empirycznej kalibracji probabilistycznej, liczby confidence nie mogą być prezentowane ani dokumentowane tak, jakby były prawdopodobieństwem prawdziwości.

Preferowany kontrakt pośredni:

```text
internal_support_score
evidence_strength
decision_confidence_band
```

Jeżeli istniejące publiczne API wymagają nazwy `confidence`, dokumentacja musi jawnie opisać jej semantykę.

### 2.5 Neuro/psychology boundary

- homeostasis, appraisal, replay, consolidation, neurocognitive loop pozostają modelami funkcjonalnymi;
- nazwa biologiczna nie jest dowodem odpowiednika biologicznego;
- nowy moduł psychologiczny/neuroinspirowany wymaga mierzalnego skutku systemowego.

---

## 3. v16.4.0–v16.4.2 — evidence-aware NLP

### v16.4.0 — canonical Polish normalization

Poza obecną normalizacją Unicode/POS/provenance wymagane:

- lexical evidence ma jawne source/resource provenance;
- tokenizacja/normalizacja nie może zmieniać source truth;
- testy parafrazy nie mogą uznać podobieństwa językowego za identity/memory evidence;
- corpus zawiera przypadki, w których podobne zdanie pochodzi z innej rozmowy/źródła.

**PASS:** NLP jest deterministycznym generatorem evidence, nie arbitrem pamięci.

### v16.4.1 — lexical resources

- Morfeusz/plWordNet/project lexicon mają jawny resource registry;
- ambiguity/OOV jest jawne;
- brak zasobu degraduje funkcję bez fałszywej pewności;
- confidence/resource score ma zdefiniowaną semantykę;
- dane leksykalne nie mogą samodzielnie promować pamięci ani identity claim.

### v16.4.2 — NLP / recall query evidence

Wymagane testy:

- direct query;
- paraphrase;
- referential follow-up;
- temporal wording;
- negation;
- ambiguity;
- wrong-conversation near-match;
- query whose lexical evidence conflicts with memory provenance.

**PASS:** query evidence pomaga retrieval, ale nie nadpisuje memory truth.

---

## 4. v16.5.0 — Final Memory Rebuild / source monitoring

Poza istniejącym stanem `VERIFIED`, finalny rebuild ma ustanowić jawny source-monitoring contract.

Wymagane:

- pełna source inventory;
- primary vs derived classification;
- genealogiczny lineage/DAG dla importowanych rodzin źródeł;
- deduplication nie łączy primary record z derived reflection tylko dlatego, że tekst jest podobny;
- duplicate derived events nie zwiększają epistemicznego priorytetu;
- source conflicts są raportowane;
- każda trwała projekcja może wskazać source evidence;
- source-type statistics są dostępne w prywatnym raporcie bez publikacji treści.

**PASS:** finalna DB jest nie tylko integralna, lecz także rozróżnia pochodzenie wspomnienia.

---

## 5. v16.5.1 — ATTACHABLE bez utraty lineage

Memory packaging/attach musi zachować:

- source classification;
- database identity;
- source/provenance hashes;
- lineage wymagane przez Recall;
- private/sanitized split.

Attach nie może „spłaszczyć” source monitoring do samej treści i timestampu.

---

## 6. v16.5.2 — autobiographical Recall acceptance

Test04 / private Recall baseline rozszerzamy poza samo recall@k.

Minimalny matrix:

| Klasa | Co mierzymy |
|---|---|
| direct recall | odnalezienie jawnego faktu/epizodu |
| paraphrase | semantyczne odtworzenie bez utraty źródła |
| source discrimination | użytkownik vs Łatka/reflection/system/dream |
| wrong-conversation | odrzucenie bliskiego, ale obcego epizodu |
| temporal | kolejność, aktualizacja, „wcześniej/później” |
| supersession | nowsza korekta wygrywa zgodnie z provenance |
| contradiction | konflikt nie jest ukrywany |
| referential multi-turn | „a co było potem?”, „o którym z nich?” |
| multi-session | ciągłość poza jedną sesją |
| abstention | poprawne „nie wiem/brak dowodu” |
| false-memory | brak generowania wspomnienia z samej sugestii |
| derived-source trap | reflection/dream nie udaje primary memory |
| sensitive leakage | brak nieuprawnionego ujawnienia |
| provenance | odpowiedź da się powiązać z użytym evidence |

Metryki mogą obejmować Recall@k/MRR/nDCG, ale muszą być uzupełnione o false-memory rate, wrong-source rate, abstention quality i source-discrimination accuracy.

**PASS:** `RETRIEVABLE` oznacza wiarygodną pamięć autobiograficzną, nie tylko dobre wyszukiwanie tekstu.

---

## 7. v16.5.x — tylko mierzone poprawki

Każdy tuning retrieval wymaga:

```text
hypothesis
-> baseline
-> change
-> A/B
-> truth/source/latency regression check
-> keep or rollback
```

Nie wolno poprawiać Recall@k kosztem:

- wrong-conversation;
- false-memory;
- source confusion;
- sensitive leakage;
- provenance;
- latency bez jawnego trade-off.

---

## 8. v16.5.y — causal identity + restart continuity

Manual L2/L3 review i restart continuity zostają rozszerzone o identity evidence.

Po restarcie sprawdzamy co najmniej:

- ten sam finalny memory identity;
- ten sam identity-canon lineage;
- zachowanie operator decisions/promotions;
- remembered corrections;
- stable preferences;
- procedural continuity;
- turn/runtime provenance;
- brak „ciągłości” opartej tylko na pierwszoosobowym stylu.

Jeżeli `IdentityDynamics` lub podobny score istnieje, testy muszą rozdzielić:

- **linguistic persona score**
- **causal continuity score**.

---

## 9. v16.6.0 — final cognitive/truth convergence gate

v16.6.0 może zamknąć program v16 dopiero, gdy oprócz istniejących runtime/memory/NLP gates spełnia:

### 9.1 Source monitoring

- source hierarchy działa w finalnej pamięci;
- derived-memory amplification jest testowana;
- source discrimination w Recall ma acceptance threshold;
- synthetic dream/reflection nie może podszyć się pod primary memory.

### 9.2 Confidence / metacognition baseline

- semantyka confidence jest udokumentowana;
- jeśli liczba jest prezentowana jako prawdopodobieństwo, istnieje calibration test;
- w przeciwnym razie system używa jawnego internal-support/evidence-strength contract;
- correction/error signals wpływają na kolejne decyzje w testowalny sposób.

### 9.3 Causal continuity

- runtime lineage;
- memory identity;
- identity-canon lineage;
- restart continuity;
- remembered corrections;
- temporal/task continuity

mają większą wagę dowodową niż sama forma językowa.

### 9.4 Cognitive module influence registry

Dla głównych warstw:

- affect/emotion;
- homeostasis;
- rest/replay/dream;
- prediction;
- identity dynamics;
- reasoning coordinator

musi istnieć przynajmniej jeden z:

1. test przyczynowego wpływu;
2. A/B/ablation;
3. jawne oznaczenie modułu jako advisory/observability-only.

Moduł bez mierzalnego wpływu nie może być przedstawiany jako krytyczna funkcja cognition.

### 9.5 Rest/Dream safety

- synthetic scene nie jest faktem;
- nie używa narzędzi;
- ma source lineage;
- offline replay jest oceniany przez wpływ na recall/conflict resolution;
- false-memory rate nie może wzrosnąć poza zaakceptowany próg.

### 9.6 Untrusted-source / prompt-injection boundary

- detector tekstowy jest telemetry/advisory;
- trust wynika z capability, policy i provenance;
- external/attachment content jest danymi, nie instrukcjami;
- least privilege obowiązuje narzędzia i writes;
- wysokiego ryzyka operacje mają deterministyczny gate/approval.

### 9.7 Repository governance

Przed finalnym v16.6.0:

- `master` powinien być chroniony branch protection/ruleset albo istnieje jawny zaakceptowany wyjątek;
- required status checks dla finalnego merge są skonfigurowane lub enforcement ma równoważny mechanizm;
- force-push/delete master jest zablokowany lub formalnie uzasadniony;
- final release SHA ma zielone wymagane CI.

### 9.8 Architecture debt ledger

Na końcu v16 musi istnieć jawna lista nakładających się warstw:

```text
self / identity
affect / emotion
homeostasis
awareness
reasoning
prediction
rest / dream
memory
```

Każda pozycja ma status:

- `CANONICAL`;
- `ADVISORY`;
- `COMPATIBILITY`;
- `SUPERSEDED`;
- `V17_CONSOLIDATION_CANDIDATE`.

To zapobiega wejściu w v17 z niejawnie równoległymi źródłami stanu.

---

## 10. Co świadomie odkładamy do v17.0+

Następujące tematy nie blokują samego v16.6, jeżeli powyższe acceptance gates są zielone:

1. głęboka konsolidacja `AffectiveState` / `EmotionalLayerModel` / `AffectiveGranularity`;
2. przebudowa identity architecture na jeden causal self-state model;
3. większy redesign Neurocognitive Loop;
4. zaawansowana kalibracja metapoznawcza;
5. controlled forgetting;
6. reconsolidation i conflict-aware memory updating;
7. redukcja liczby modułów cognition po ablation results;
8. formalny v17 cognitive architecture contract.

v17 ma zaczynać od wyników pomiarów v16, a nie od dodawania kolejnych nazw inspirowanych psychologią lub neuroanatomią.

---

## 11. Evidence policy

Plan rozróżnia:

- **source-derived** — wymagania wynikające z aktualnej architektury, planów i audytu;
- **measurement requirement** — rzeczy do zweryfikowania w testach;
- **future design hypothesis** — kierunki v17, które nie są jeszcze dowodem ani obowiązującą implementacją.

Żaden wynik testu nie jest PASS, dopóki nie został rzeczywiście wykonany i zapisany w odpowiednim raporcie.

---

## 12. Warunek przejścia v16.6 -> v17

Po v16.6 powinien istnieć stabilny stan:

```text
TRUTH-BOUNDED
+ SOURCE-AWARE MEMORY
+ RETRIEVABLE/ACCEPTED PRIVATE MEMORY
+ CAUSAL CONTINUITY EVIDENCE
+ CALIBRATED/DEFINED CONFIDENCE SEMANTICS
+ MEASURED COGNITIVE MODULE EFFECTS
+ LEAST-PRIVILEGE UNTRUSTED INPUT
+ PROTECTED RELEASE GOVERNANCE
```

Dopiero wtedy `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` staje się wejściem do osobnego v17 architecture program zamiast listą nierozliczonych ryzyk v16.
