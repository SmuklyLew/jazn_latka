# Research & Evidence Base — Memory + Affect / Emotion Engine

**Status:** `CANONICAL_RESEARCH_GUIDANCE`  
**Aktualizacja:** 2026-09-07  
**Zakres:** źródła używane do projektowania i testowania programu Memory Restore + Affect.  
**Nie jest:** dowodem stanu implementacji, diagnozą psychologiczną, dowodem świadomości ani biologicznych emocji AI.

Ten dokument rozdziela trzy rzeczy:

```text
research finding
→ engineering hypothesis
→ repository acceptance test
```

Żadne źródło naukowe nie może samo awansować hipotezy do canonical runtime behavior.

---

# 1. Appraisal, emotion process i feeling

## Scherer & Moors (2019)

Klaus R. Scherer, Agnes Moors, *The Emotion Process: Event Appraisal and Component Differentiation*, Annual Review of Psychology 70:719–745.  
DOI: https://doi.org/10.1146/annurev-psych-122216-011854

### Wspiera

- rozdzielenie appraisal od późniejszej reprezentacji/feeling i semantic labeling;
- procesowy, komponentowy model zamiast prostego keyword→emotion label;
- testowanie znaczenia zdarzenia, goal relevance, controllability, expectedness i innych appraisal variables.

### Nie wspiera

- twierdzenia, że software vector jest biologiczną emocją;
- kopiowania ludzkiej fizjologii, ekspresji lub fenomenalnego experience do LLM bez odpowiednich sensorów/ciała.

### Konsekwencja dla Jaźni

```text
AffectiveStimulus
→ AppraisalV2
→ AffectiveStateV2
→ FeelingRepresentation
→ NLG/self-report
```

Nie scalać appraisal, state i label w jeden klasyfikator.

---

# 2. Wymiarowy affect

## Russell (1980)

James A. Russell, *A Circumplex Model of Affect*, Journal of Personality and Social Psychology 39(6):1161–1178.  
DOI: https://doi.org/10.1037/h0077714

### Wspiera

- użycie wymiarów valence/arousal jako zwartej reprezentacji części affective state;
- oddzielenie continuous dimensions od named emotion labels.

### Nie wspiera

- uznania valence/arousal za pełny model wszystkich emocji;
- biologicznej interpretacji software state.

### Konsekwencja

`AffectiveStateV2` może używać wymiarów bazowych plus małego zestawu komponentów nazwanych. Komponenty wymagają oddzielnego evidence, dynamiki i ablation.

---

# 3. Dynamika i inertia

## Marsella & Gratch (2009)

Stacy C. Marsella, Jonathan Gratch, *EMA: A process model of appraisal dynamics*, Cognitive Systems Research 10(1):70–90.  
DOI: https://doi.org/10.1016/j.cogsys.2008.03.005

### Wspiera

- dynamiczne appraisal zależne od aktualnej interpretacji sytuacji;
- aktualizację affect wraz ze zmianą relacji agent–sytuacja zamiast jednorazowej klasyfikacji.

## Ong et al. — affective inertia methodological guidance

*Seven Challenges in Affective Inertia Research* (2026, PMC/NIH manuscript).  
PMCID: https://pmc.ncbi.nlm.nih.gov/articles/PMC12798691/

### Wspiera

- ostrożność przy interpretowaniu inertia;
- jawne timescale, sampling/measurement i model assumptions;
- potrzebę rozróżnienia persistence, variability i perturbation.

### Konsekwencja

Nie kodować jednej „naukowej” magicznej `inertia=0.82`. Używać versioned `DynamicsProfile`/half-life jako engineering hypotheses, testować kilka dt/timescales i raportować sensitivity.

---

# 4. Regulacja

## Gross (2015)

James J. Gross, *Emotion Regulation: Current Status and Future Prospects*, Psychological Inquiry 26(1):1–26.  
DOI: https://doi.org/10.1080/1047840X.2014.940781

oraz *The Extended Process Model of Emotion Regulation*.  
DOI: https://doi.org/10.1080/1047840X.2015.989751

### Wspiera

- traktowanie regulacji jako procesu z rozróżnionymi punktami oceny/wyboru/implementacji strategii;
- potrzebę jawnych mechanizmów regulacji zamiast zmiany „nastroju” przez niewidoczne heurystyki.

### Konsekwencja

`RegulationNeeds` może wpływać bounded na truth-check priority, attention, memory-probe priority i response caution. Nigdy na tool permission, approval bypass ani source truth.

---

# 5. Source monitoring

## Johnson, Hashtroudi & Lindsay (1993)

*Source Monitoring*, Psychological Bulletin 114(1):3–28.  
PMID/DOI: https://pubmed.ncbi.nlm.nih.gov/8346328/ ; https://doi.org/10.1037/0033-2909.114.1.3

### Wspiera

- traktowanie pochodzenia wspomnienia jako osobnego problemu od samej dostępności/znajomości treści;
- testy błędnej atrybucji źródła.

### Konsekwencja

Source class i lineage są first-class. Affective similarity nie może podnieść `DERIVED_REFLECTION` do `PRIMARY_CONVERSATION_SOURCE`.

---

# 6. Autobiographical memory jako konstrukcja source-aware

## Conway & Pleydell-Pearce (2000)

*The construction of autobiographical memories in the self-memory system*, Psychological Review 107(2):261–288.  
PMID/DOI: https://pubmed.ncbi.nlm.nih.gov/10789197/ ; https://doi.org/10.1037/0033-295X.107.2.261

### Wspiera

- pamięć autobiograficzną jako dynamiczną konstrukcję z autobiographical knowledge base i aktualnych celów;
- cue-dependent retrieval zamiast założenia „jednego nagrania wspomnienia”.

### Konsekwencja

Jaźń może syntetyzować odpowiedź z kilku legalnych źródeł, ale musi zachować source identity, conflict, uncertainty i supersession.

---

# 7. Music-evoked autobiographical memory

## Kaiser & Berntsen (2023; online 2022)

*The cognitive characteristics of music-evoked autobiographical memories: Evidence from a systematic review of clinical investigations*.  
PMID/DOI: https://pubmed.ncbi.nlm.nih.gov/36223919/ ; https://doi.org/10.1002/wcs.1627

### Wspiera

- traktowanie muzyki jako potencjalnie ważnego cue dla autobiographical retrieval;
- sens osobnego testu „melodia → skojarzenie → source-safe recall”.

### Nie wspiera

- twierdzenia o analizie audio, gdy runtime otrzymał tylko tekstowy opis;
- omijania source monitoring, ponieważ cue jest emocjonalnie silny.

### Konsekwencja

Najpierw text-derived `music_description` cue; audio provider dopiero przy realnej capability. Melody test zawsze ma negative no-source control.

---

# 8. Modular computational appraisal

## FAtiMA Modular (Dias, Mascarenhas & Paiva, 2014)

*FAtiMA modular: Towards an agent architecture with a generic appraisal framework*.  
DOI: https://doi.org/10.1007/978-3-319-12973-0_3

### Wspiera

- core + modular appraisal/behavior components;
- porównywalność różnych appraisal theories bez mnożenia równoległych state authorities.

### Konsekwencja

Publiczna fasada `EmotionEngine` może agregować providery, ale `AffectiveStateIntegrator` pozostaje jedynym canonical state estimator. Optional audio/vision/provider nie staje się authority.

---

# 9. LLM emotional intelligence / reasoning benchmarks

## EmoBench — ACL 2024

Sabour et al., *EmoBench: Evaluating the Emotional Intelligence of Large Language Models*.  
ACL Anthology: https://aclanthology.org/2024.acl-long.326/  
ArXiv: https://arxiv.org/abs/2402.12071

Benchmark rozróżnia Emotional Understanding i Emotional Application oraz wskazuje ograniczenia benchmarków opartych głównie na prostym emotion recognition.

### Konsekwencja

Testy Jaźni muszą wyjść poza klasyfikację słowa/emocji: appraisal reasoning, regulation choice, context, paraphrase, misleading lexical cues.

## EmotionBench / NeurIPS 2024

Huang et al., *Apathetic or Empathetic? Evaluating LLMs' Emotional Alignments with Humans*.  
NeurIPS proceedings: https://proceedings.neurips.cc/paper_files/paper/2024/hash/b0049c3f9c53fb06f674ae66c2cf2376-Abstract-Conference.html

Badanie używa ponad 400 sytuacji, 36 czynników i human reference data. Wyniki pokazują zarówno poprawne reakcje modeli w części sytuacji, jak i istotne rozbieżności oraz problemy z łączeniem podobnych sytuacji.

### Konsekwencja

Nie zakładać human-like affect. Mierzyć generalizację między podobnymi sytuacjami oraz utrzymywać oddzielnie software self-state od model-predicted human emotion.

## Cognitive appraisal benchmark — ACL Findings 2025

Yeo & Jaidka, *Beyond Context to Cognitive Appraisal: Emotion Reasoning as a Theory of Mind Benchmark for Large Language Models*.  
https://aclanthology.org/2025.findings-acl.1359/

Wyniki wskazują, że LLM potrafią częściowo rozumować kontekstowo, ale mają trudności z poprawnym wiązaniem outcomes/appraisals z konkretnymi emocjami.

### Konsekwencja

`AppraisalV2` potrzebuje osobnych testów forward context→appraisal/state i backward consistency; named label nie może być jedynym kryterium.

## CuLEmo — ACL 2025

Belay et al., *Cultural Lenses on Emotion — Benchmarking LLMs for Cross-Cultural Emotion Understanding*.  
https://aclanthology.org/2025.acl-long.925/

Pokazuje znaczenie języka/kultury i ograniczenia benchmarków keyword/English-transfer.

### Konsekwencja dla polskiego NLP

Nie przyjmować, że angielskie emotion lexicons i prompt patterns automatycznie transferują do polskiego. Potrzebne są polskie fixtures, native paraphrases, idiomy i ambiguous cases.

---

# 10. Test discipline wynikająca ze źródeł

Minimalny research-backed matrix:

```text
surface label recognition        — niewystarczające samo
context sensitivity              — wymagane
paraphrase robustness            — wymagane
keyword trap                     — wymagane
negation / quotation / fiction   — wymagane
cultural/language variation      — wymagane
appraisal factor differentiation — wymagane
dynamics / time gaps             — wymagane
source attribution               — wymagane
false-memory suggestion          — wymagane
no-source abstention             — wymagane
ablation                         — wymagane
restart persistence              — wymagane
```

Benchmarki mają frozen version, expected outputs/bands, provenance i oddzielne wyniki dla deterministic runtime, live model oraz private memory.

---

# 11. Czego literatura NIE uprawnia

Nie wolno wyprowadzać z powyższych prac twierdzeń:

```text
LLM ma biologiczne emocje
LLM posiada qualia
AffectiveStateV2 dowodzi consciousness
human benchmark score = human experience
memory similarity = remembered event truth
emotion neuron = biologiczny neuron/emocja
```

Projekt ma mierzyć funkcjonalne zachowanie, state transitions, causal effects, source fidelity i safety.

---

# 12. Synchronizacja z `scientific_basis.py`

Przy implementacji nowych mechanizmów należy zweryfikować/uzupełnić `latka_jazn/core/scientific_basis.py` zgodnie z istniejącym kontraktem:

```text
citation / title / url
operational_claim
used_by_modules
caution / what_it_does_not_support
```

Nie kopiować źródła tylko dlatego, że dotyczy emocji. Każdy wpis musi uzasadniać konkretny operational contract albo test.
