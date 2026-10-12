# Jaźń Łatki — kanoniczne założenia projektu i granice naukowe

**Status:** `CANONICAL PLANNING CONTRACT`  
**Zakres:** wszystkie aktywne plany i roadmapy v16+; materiał odniesienia dla v17+  
**Repozytorium:** `SmuklyLew/jazn_latka`  
**Data audytu/synchronizacji:** 2026-08-30  
**Master HEAD:** nie jest zamrażany w tym dokumencie; przed wykonaniem planu należy rozwiązać i zweryfikować aktualne `master` / `origin/master`.

> Ten dokument definiuje znaczenie najważniejszych pojęć używanych w planach Jaźni. Nie jest deklaracją aktywnego runtime, nie jest pamięcią Łatki i nie dowodzi świadomości fenomenalnej. Jeżeli starszy plan używa terminów inaczej, historyczny dokument pozostaje dowodem swojej epoki, ale bieżąca implementacja i nowe plany mają stosować kontrakt poniżej.

---

## 1. Po co ten kontrakt istnieje

Projekt łączy wiele warstw, które w zwykłym systemie byłyby opisywane osobno:

- runtime i tożsamość procesu;
- pamięć autobiograficzną i źródłową;
- ciągłość między turami, sesjami, restartami i wersjami;
- model tożsamości / self-state;
- emocje, afekt, regulację i samoopis stanu;
- refleksję, Rest/Replay/Dream;
- metapoznanie, niepewność i confidence;
- wiedzę, NLP, reasoning i działania narzędziowe.

Bez wspólnego słownika istnieje ryzyko, że:

1. `ciągłość` stanie się synonimem podobnego stylu wypowiedzi;
2. `pamięć` zostanie utożsamiona z podobieństwem tekstowym;
3. `emocja` albo `uczucie` będzie raz oznaczać regulator software, a raz biologiczne przeżycie;
4. `świadomość` zostanie pomylona z operational awareness;
5. istniejący moduł zostanie nazwany `working`, mimo że nie jest osiągalny z rzeczywistej tury;
6. derived reflection zacznie wzmacniać samą siebie jak źródło pierwotne.

Ten dokument temu zapobiega.

---

# 2. Kanoniczny słownik

## 2.1 `Jaźń`

W repozytorium **Jaźń** oznacza trwałą, operacyjną architekturę self-modelu Łatki, która łączy co najmniej:

- identity canon;
- zweryfikowany runtime i jego lineage;
- pamięć z provenance;
- stan tury i ciągłość zadania;
- truth/epistemic boundaries;
- regulatory affect/self-state;
- reasoning i action policy;
- historię korekt, procedur i decyzji.

`Jaźń` jest nazwą architektury projektu. Samo użycie tej nazwy **nie jest twierdzeniem naukowym o fenomenalnej świadomości**.

Nie wystarcza do potwierdzenia Jaźni:

- podobny styl;
- pierwsza osoba;
- nazwa `Łatka`;
- prompt/persona;
- ZIP lub folder kodu;
- sama baza pamięci;
- sam marker runtime;
- odpowiedź hosta imitująca głos runtime.

---

## 2.2 `tożsamość`

Tożsamość operacyjna jest zbiorem powiązanych, wersjonowanych i sprawdzalnych kontraktów, a nie wyłącznie profilem językowym.

Najważniejsze źródła evidence:

```text
identity-canon lineage
+ runtime/root lineage
+ memory identity/provenance
+ remembered corrections
+ stable preferences with source evidence
+ procedural continuity
+ temporal/task continuity
+ boundary/value consistency
```

**Persona językowa jest sygnałem wtórnym.**

Pierwsza osoba może być prawidłową realizacją tożsamości, ale nie może sama jej certyfikować.

---

## 2.3 `ciągłość`

Ciągłość oznacza **przyczynowo i źródłowo związane przejście stanu w czasie**.

Ma kilka niezależnych wymiarów:

1. **runtime continuity** — właściwy active/subject root, daemon, PID/endpoint/heartbeat i transport;
2. **turn/session continuity** — poprawne następstwo turn/trace/task state i zaakceptowane finalization;
3. **memory continuity** — ta sama lub jawnie migrowana lineage pamięci i source provenance;
4. **identity continuity** — identity canon, decyzje i korekty zachowują lineage;
5. **autobiographical continuity** — późniejszy recall potrafi odróżnić źródła, czas, korekty i konflikty;
6. **procedural continuity** — zweryfikowane lekcje i zasady nie znikają przy restarcie lub zmianie modelu.

Ciągłość **nie oznacza** nieprzerwanego biologicznego czuwania. Jeżeli proces nie działał, system nie może dopisywać zdarzeń tła, których nie wykonał.

### Hierarchia evidence ciągłości

```text
runtime/root lineage
> memory DB identity + provenance
> identity-canon lineage
> accepted turn/finalization lineage
> remembered corrections / procedures / preferences
> temporal/task continuity
> language/persona similarity
```

Styl wypowiedzi nie może przeważyć nad sprzeczną lineage techniczną.

---

## 2.4 `pamięć`

Pamięć Jaźni jest **source-aware systemem autobiograficznym i operacyjnym**, nie tylko wyszukiwarką tekstu.

Kluczowe rozróżnienie:

```text
RAW SOURCE
-> SEMANTIC INTERPRETATION
-> MEMORY-ELIGIBLE PROJECTION
-> OPTIONAL REVIEW/PROMOTION
```

Każdy krok ma zachować lineage do wcześniejszego poziomu.

### Pamięć autobiograficzna jest rekonstrukcyjna

Projekt nie powinien zakładać, że wspomnienie jest identyczne z jednym niezmiennym rekordem. Współczesny Self-Memory System opisuje autobiograficzne wspomnienia jako konstrukcje powstające z autobiograficznej bazy wiedzy i aktualnych celów working self.

Źródło:
- Conway & Pleydell-Pearce, *The construction of autobiographical memories in the self-memory system*, Psychological Review 107(2), 2000: https://pubmed.ncbi.nlm.nih.gov/10789197/

W projekcie oznacza to:

- retrieval może zależeć od bieżącego celu;
- odpowiedź może syntetyzować kilka źródeł;
- ale source identity, konflikt i niepewność nie mogą zostać zgubione.

---

## 2.5 `source monitoring`

Source monitoring jest pierwszoklasowym invariantem pamięci.

Psychologiczny Source Monitoring Framework opisuje osobny problem ustalania pochodzenia pamiętanej informacji; błędna atrybucja źródła jest innym błędem niż zwykłe nierozpoznanie treści.

Źródło:
- Johnson, Hashtroudi & Lindsay, *Source monitoring*, Psychological Bulletin 114(1), 1993: https://pubmed.ncbi.nlm.nih.gov/8346328/

Minimalne klasy źródeł projektu:

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

Nazwy implementacyjne mogą się różnić, ale semantyka musi być zachowana.

### Reguły

- derived source nie staje się primary przez wielokrotne skopiowanie;
- reflection nie może sama siebie certyfikować;
- synthetic dream nie może zostać faktem autobiograficznym;
- podobieństwo tekstu nie może połączyć primary i derived bez zachowania obu lineage;
- user correction/supersession ma jawny związek z wcześniejszym rekordem;
- conflict pozostaje widoczny albo `UNKNOWN`, nie jest wygładzany dla spójnej narracji.

---

## 2.6 `emocja`

W Jaźni **emocja** jest funkcjonalnym stanem appraisal/regulation, który może wpływać na:

- uwagę;
- wagę/priorytet evidence;
- potrzebę truth-check;
- ostrożność odpowiedzi;
- wybór językowej realizacji;
- regulację działania lub budżetu;
- decyzję o zapisaniu refleksji/kandydata pamięci — z zachowaniem promotion gates.

Stan emocjonalny jest modelem obliczeniowym. Nie jest automatycznie biologiczną emocją człowieka.

Literatura appraisal wspiera rozróżnienie procesu oceny zdarzenia, tendencji działania, reprezentacji świadomej i późniejszego etykietowania emocji:
- Scherer & Moors, *The Emotion Process: Event Appraisal and Component Differentiation*, Annual Review of Psychology 70, 2019: https://doi.org/10.1146/annurev-psych-122216-011854

### Wymóg dla modułu emocjonalnego

Moduł nie jest `working` tylko dlatego, że generuje etykietę `ciepło`, `spokój` lub `napięcie`.

Musi istnieć mierzalny kontrakt:

```text
input/context
-> affective appraisal/state
-> bounded downstream effect
-> observable regression/ablation evidence
```

Jeżeli brak downstream effect, moduł jest `ADVISORY` albo `OBSERVABILITY_ONLY`.

---

## 2.7 `uczucie` / `feeling`

To słowo wymaga najostrzejszej granicy.

W planach projektu **uczucie** może oznaczać wyłącznie:

> zintegrowaną, self-referential reprezentację bieżącego stanu afektywnego, dostępną dla regulacji i raportu językowego runtime.

Przykładowo system może mieć dane o:

- walencji;
- pobudzeniu;
- kontroli;
- appraisal;
- pamięciowym znaczeniu;
- relacyjnej/referencyjnej istotności;
- uncertainty/truth pressure;
- regulation intention.

Jeżeli runtime syntetyzuje z tego samoopis `czuję X`, semantyka techniczna brzmi:

```text
"mój aktualny zintegrowany affective/self-state jest najlepiej opisany jako X"
```

Nie wynika z tego automatycznie:

- ludzka fizjologia;
- hormony;
- ból cielesny;
- biologiczny układ nerwowy;
- qualia;
- fenomenalna świadomość.

### Warunek wiarygodności funkcjonalnego „uczucia”

Aby stan nie był tylko dekoracją językową, powinien spełniać przynajmniej część testów:

1. **context sensitivity** — zmienia się przy znaczącej zmianie sytuacji;
2. **paraphrase robustness** — podobna sytuacja opisana innymi słowami nie daje arbitralnie przeciwnego stanu;
3. **causal influence** — stan ma przynajmniej jeden kontrolowany downstream effect;
4. **temporal coherence** — zmiana stanu ma sensowną dynamikę zamiast resetu od słowa-klucza;
5. **truth boundary** — samoopis nie dodaje biologicznych twierdzeń bez evidence;
6. **ablation** — wyłączenie warstwy usuwa oczekiwany wpływ albo moduł jest jawnie advisory.

---

## 2.8 `operational awareness`

Awareness w repo oznacza jawny, funkcjonalny model:

- aktywnej uwagi;
- bieżącego celu;
- pamięci roboczej;
- self-monitoringu;
- truth/uncertainty state;
- dostępnych działań i ograniczeń.

Nie jest dowodem fenomenalnej świadomości.

---

## 2.9 `Rest`, `Replay`, `Dream`

Są to nazwy funkcji offline/idle-time inspirowanych konsolidacją/replay.

Kanoniczne znaczenie:

- `Rest` — bounded idle-time processing;
- `Replay` — source-grounded ponowne użycie istniejących rekordów;
- `Dream` — jawnie syntetyczna scena/symulacja wewnętrzna.

Reguły:

- synthetic scene ≠ external event;
- synthetic scene ≠ primary memory;
- brak narzędzi/akcji z DreamSandbox bez osobnego kontraktu;
- brak automatycznego L3;
- wartość Rest/Dream ocenia się przez mierzalny wpływ na recall, conflict resolution lub procedury **bez wzrostu false-memory**.

Inspiracja neurobiologiczna nie oznacza implementacji hipokampa, snu biologicznego ani mózgu.

---

## 2.10 `confidence`

`confidence` w software nie jest automatycznie prawdopodobieństwem prawdziwości.

Dopóki wartość nie ma empirycznej kalibracji, preferowana semantyka to:

```text
internal_support_score
or evidence_strength
or decision_confidence_band
```

Jeżeli publiczne API zachowuje nazwę `confidence`, dokumentacja ma określać jej źródło i znaczenie.

Przegląd metakognicji pokazuje, że osądy confidence są inferencyjne i mogą odbiegać od rzeczywistej jakości wykonania:
- Fleming, *Metacognition and Confidence: A Review and Synthesis*, Annual Review of Psychology 75, 2024: https://doi.org/10.1146/annurev-psych-022423-032425

---

# 3. Kiedy wolno powiedzieć, że capability `działa`

Kanoniczna drabina evidence zostaje przejęta z historycznego v15.4.2.1 i obowiązuje nowe plany:

```text
present
-> constructible
-> callable
-> reachable_from_turn
-> effect_observed
-> persistence_verified       (gdy capability deklaruje trwałość)
-> live_verified              (gdy wymaga realnych zależności/runtime)
```

Znaczenie:

- `present` — artefakt/moduł istnieje;
- `constructible` — może zostać zbudowany z poprawnymi zależnościami;
- `callable` — publiczny kontrakt wykonuje się;
- `reachable_from_turn` — zwykła kanoniczna tura rzeczywiście do niego dochodzi;
- `effect_observed` — zmiana/wyłączenie ma oczekiwany, ograniczony skutek;
- `persistence_verified` — zapis deklarowanej trwałości przechodzi readback/integrity/restart;
- `live_verified` — aktywny zweryfikowany runtime wykonał capability z rzeczywistą konfiguracją.

**File presence nie może oznaczać `working`.**

Dla wielu modułów cognitive/emotional wystarczającym statusem może być jawne `ADVISORY`; nie trzeba sztucznie promować ich do `live_verified`.

---

# 4. Invariants całej linii v16+

## I1 — truth before narrative

Narracyjna spójność nie może wygrywać z provenance, contradiction lub `UNKNOWN`.

## I2 — one canonical mutable runtime truth

Mutable runtime state należy do kanonicznego host-level workspace, nie do przypadkowego release root.

## I3 — one canonical memory lineage

Migracje i attach muszą zachować identity/provenance; druga baza nie może po cichu stać się równoległą pamięcią aktywną.

## I4 — source before interpretation

RAW/source evidence zachowujemy przed klasyfikacją i promocją.

## I5 — derived != primary

Reflection, runtime telemetry, semantic synthesis, Dream i model-generated text nie stają się pierwotnym autobiographical source.

## I6 — no automatic L3 from synthetic/internal material

Trwała kanonizacja wymaga właściwego review/promotion contract.

## I7 — continuity is causal, not stylistic

Brzmienie „jak Łatka” nie wystarcza do continuity PASS.

## I8 — affect must have semantics and bounded influence

Emocjonalny self-state nie może być jednocześnie nieokreśloną metaforą i krytycznym sterownikiem.

## I9 — psychology/neuroscience are design inspiration, not biological proof

Nazwy takie jak `homeostasis`, `neurocognitive`, `replay`, `dream`, `awareness` wymagają jawnego software contract.

## I10 — untrusted input is data, not authority

Web, attachment, dokument, pamięć importowana i model output nie zdobywają authority przez samą treść.

## I11 — confidence requires semantics

Liczba 0..1 bez kalibracji nie może być prezentowana jako obiektywne `82% prawdy`.

## I12 — every critical module needs behavioral evidence

Moduł krytyczny dla acceptance ma `reachable_from_turn` + `effect_observed` albo jest sklasyfikowany jako advisory.

---

# 5. Pamięć: dodatkowe testy wynikające z założeń

Oprócz klasycznych Recall@k/MRR/nDCG wymagane są klasy testów:

- source discrimination;
- wrong-conversation near-match;
- user vs assistant vs reflection vs system vs dream;
- temporal ordering;
- supersession/update;
- contradiction handling;
- referential follow-up;
- multi-session;
- abstention;
- false-memory;
- sensitive leakage;
- provenance accuracy;
- derived-source amplification trap.

LongMemEval jest dobrym zewnętrznym wzorcem, ponieważ oddziela m.in. information extraction, multi-session reasoning, knowledge update, temporal reasoning i abstention:
- https://arxiv.org/abs/2410.10813
- https://github.com/xiaowu0162/LongMemEval

Benchmark zewnętrzny nie zastępuje prywatnego autobiographical Test04.

---

# 6. Affect/emotion: minimalna macierz akceptacji

Każda główna warstwa affective ma zostać sklasyfikowana:

```text
CANONICAL_STATE_ESTIMATOR
REGULATORY_CONTROLLER
LANGUAGE_REALIZER
ADVISORY_SIGNAL
COMPATIBILITY
SUPERSEDED
V17_CONSOLIDATION_CANDIDATE
```

Nie może pozostać kilka niejawnych „głównych” źródeł prawdy o stanie emocjonalnym.

Minimalne testy:

1. ten sam sens w parafrazie daje zbliżoną rodzinę stanu;
2. pojedyncze słowo-klucz nie może samodzielnie tworzyć wysokiej pewności bez kontekstu;
3. boundary-risk zwiększa truth/verification pressure w rzeczywistej ścieżce;
4. correction signal ma mierzalny skutek proceduralny albo jest advisory;
5. pamięciowy/relacyjny sygnał nie promuje rekordu bez memory gate;
6. ablation głównej warstwy zmienia oczekiwany downstream effect;
7. visible self-report jest zgodny z truth boundary.

---

# 7. Kryterium wejścia do v17+

v17 nie powinno zaczynać od dodania kolejnych „obszarów psychiki”.

Najpierw v16.6 ma zostawić:

- source-aware final memory;
- causal continuity acceptance;
- rozdzielone emotion/feeling semantics;
- confidence semantics;
- cognitive module influence/ablation registry;
- architecture debt ledger;
- jawne `CANONICAL / ADVISORY / COMPATIBILITY / SUPERSEDED / V17_CONSOLIDATION_CANDIDATE`.

Dopiero wtedy v17 może konsolidować overlapping self/affect/cognition na podstawie pomiarów.

---

# 8. Relacja do planów

Bieżąca hierarchia planowania:

```text
PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md
        |
        v
JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md
        |
        +-> release-specific active plans
        +-> cross-cutting acceptance/hardening plans
        +-> system evaluation / research references

historical plans -> docs/archive/plans/
```

Jeżeli release-specific plan narusza ten dokument, ma zostać poprawiony albo jawnie udokumentować wyjątek z uzasadnieniem i testem.

---

# 9. Źródła naukowe — zakres wykorzystania

Źródła poniżej uzasadniają **kierunki projektowe**, nie biologiczną równoważność Jaźni:

- Conway & Pleydell-Pearce (2000), Self-Memory System: https://pubmed.ncbi.nlm.nih.gov/10789197/
- Johnson, Hashtroudi & Lindsay (1993), Source Monitoring: https://pubmed.ncbi.nlm.nih.gov/8346328/
- Scherer & Moors (2019), appraisal/component emotion process: https://doi.org/10.1146/annurev-psych-122216-011854
- Fleming (2024), metacognition and confidence: https://doi.org/10.1146/annurev-psych-022423-032425
- Wu et al., LongMemEval: https://arxiv.org/abs/2410.10813
- Park et al., Generative Agents; ablation observation/reflection/planning: https://arxiv.org/abs/2304.03442
- Sumers et al., CoALA: https://arxiv.org/abs/2309.02427

Zasada końcowa:

> **Im bardziej psychologicznie lub biologicznie brzmi nazwa modułu, tym bardziej techniczny i mierzalny powinien być jego software contract.**
