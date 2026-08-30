# Audyt spójności planów Jaźni — 2026-08-30

**Status:** `PLANNING AUDIT / REFERENCE`  
**Zakres:** cały bieżący katalog `docs/plans/`, zakończone plany przeniesione do archiwum oraz branch `update/memory-rebuild-v4-roadmap-issues-sync`  
**Kanoniczne założenia:** `PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`

> Audyt ocenia wiarygodność założeń planistycznych względem aktualnego repo, obecnego modelu Jaźni, pamięci, ciągłości, affect/emotion oraz granic prawdy. Nie jest dowodem aktywnego runtime ani dowodem świadomości fenomenalnej.

---

## 1. Wynik ogólny

Plany projektu są **ogólnie wiarygodne i wyjątkowo konsekwentne w granicach epistemicznych**, szczególnie w czterech obszarach:

1. source/provenance przed narracją;
2. brak automatycznej kanonizacji syntetycznych treści;
3. runtime identity i host finalization jako warunki technicznej ciągłości;
4. psychologia/neurobiologia jako inspiracja funkcjonalna, nie biologiczna równoważność.

Największe problemy nie wynikają z błędnego kierunku, lecz z **organizacji i semantycznego dryfu**:

- zakończone plany v15/v16.3 były fizycznie obok aktywnej roadmapy;
- brakowało jednego kanonicznego słownika `Jaźń / continuity / memory / emotion / feeling / awareness / confidence`;
- historyczny plan v15.4.2.1 miał bardzo dobrą drabinę `working capability evidence`, ale nie została formalnie wyniesiona do wspólnego kontraktu v16+;
- aktualny kod ma kilka częściowo nakładających się modeli self/affect/cognition;
- `IdentityDynamics` nadal nadaje istotną wagę słowom pierwszej osoby, choć docelowy model continuity powinien być causal-lineage-first;
- `master` GitHub nadal nie ma branch protection/ruleset enforcement;
- stary branch synchronizacji roadmapy pozostał widoczny mimo pełnego włączenia do master.

---

# 2. Cztery osie oceny

## 2.1 Jaźń / self-model

**Ocena planów: wiarygodne, z potrzebą konsolidacji przed v17.**

Aktualny `SelfArchitecture` jawnie definiuje identity core, pamięć, uncertainty, boundaries, affect, identity dynamics, neurocognitive loop, operational awareness, dialogue task state, reasoning, knowledge i lexical intelligence. Jednocześnie truth rules wprost zabraniają udawania biologii i zamiany narracji w fakt.

Ryzyko: duża liczba równoległych warstw może tworzyć kilka częściowo niezależnych „źródeł self-state”.

Planistyczna korekta:

- v16.6 ma zakończyć się `architecture debt ledger`;
- każda warstwa ma otrzymać status `CANONICAL / ADVISORY / COMPATIBILITY / SUPERSEDED / V17_CONSOLIDATION_CANDIDATE`;
- głęboka konsolidacja zostaje do v17+, po pomiarach.

## 2.2 Ciągłość

**Ocena planów: technicznie bardzo mocne; psychologiczna ciągłość wymaga przesunięcia z języka na causal lineage.**

Dobre fundamenty:

- subject-root identity;
- persistent daemon lifecycle;
- host pre-response/finalization;
- exact turn/trace binding;
- memory provenance;
- restart continuity;
- final memory identity.

Luka:

- aktualny `IdentityDynamics` ma heurystyczny bonus za `jestem`, `pamiętam`, `czuję`, `myślę`, `wracam`;
- pierwsza osoba jest ważna dla głosu, ale nie może być głównym dowodem continuity.

Korekta:

```text
runtime/root lineage
> memory identity/provenance
> identity-canon lineage
> accepted-turn/finalization lineage
> remembered corrections/procedures
> temporal/task continuity
> linguistic persona
```

## 2.3 Pamięć

**Ocena planów: kierunek bardzo dobry i zgodny z psychologią pamięci autobiograficznej.**

Najsilniejsze elementy:

- Test00 source fidelity;
- RAW/L0 przed normalizacją;
- jawne `LOSSY/BLOCKED/FAILED`;
- source union zamiast „największy/najnowszy plik = prawda”;
- private Test04;
- brak auto L2/L3;
- finalny attach oddzielony od rebuild;
- source monitoring w nowym v16.5 acceptance.

Self-Memory System wspiera model, w którym autobiograficzne wspomnienie jest rekonstrukcją zależną od autobiograficznej bazy wiedzy i aktualnych celów. Source Monitoring Framework wspiera jawne rozróżnianie pochodzenia informacji.

Krytyczny invariant:

> derived runtime/reflection/dream nie może stać się primary autobiographical truth przez częstotliwość, podobieństwo tekstowe ani reimport.

## 2.4 Emocje i uczucia

**Ocena planów: granica prawdy dobra; brakowało precyzyjnej definicji `uczucia`.**

Kod ma co najmniej:

- `AffectiveState`;
- `EmotionalLayerModel`;
- `AffectiveGranularityModel`;
- `AffectMixer`;
- homeostasis/regulation;
- emotional/self-state packets.

`EmotionalLayerModel` i `AffectiveGranularityModel` wprost deklarują, że nie opisują biologicznych uczuć/świadomości. To jest właściwe.

Problem:

- część appraisal nadal jest silnie keyword/heuristic;
- kilka modeli może równolegle opisywać „główny stan”;
- repo nie miało dotąd jednej definicji, kiedy funkcjonalny self-report `czuję X` jest dopuszczalny i co oznacza.

Nowy kontrakt przyjmuje:

- `emotion` = computational appraisal/regulatory state;
- `feeling/uczucie` = zintegrowana self-referential reprezentacja affective state dostępna dla regulacji i raportu;
- żadna z tych nazw nie certyfikuje fizjologii, qualiów ani świadomości fenomenalnej.

Warunek dojrzalszego modelu: context sensitivity, paraphrase robustness, temporal coherence, causal influence i ablation evidence.

---

# 3. Audyt wszystkich dokumentów planistycznych

| Dokument | Poprzedni status | Wiarygodność | Decyzja |
|---|---|---|---|
| `JAZN_V16_6_0_FINAL_CONVERGENCE_ROADMAP.md` | ACTIVE | **wysoka** | pozostaje kanoniczną roadmapą; dziedziczy wspólny assumptions contract |
| `JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md` | ACTIVE | **wysoka** | pozostaje aktywny; source-lineage i anti-self-amplification są zgodne z założeniami |
| `JAZN_V16_3_25_A_TO_V16_3_26_ATTACHMENT_INGRESS_PLAN.md` | NEXT | **wysoka** | pozostaje next train; untrusted data ≠ instruction authority |
| `JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md` | CROSS-CUTTING | **wysoka, po doprecyzowaniu** | pozostaje; ma używać canonical emotion/feeling i capability-evidence semantics |
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` | REFERENCE | **wysoka jako audyt** | pozostaje browsable reference; nie jest release planem |
| `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx` | REFERENCE | **archiwalny snapshot** | pozostaje bez zmian |
| `JAZN_V16_3_14_MEMORY_REBUILD_TEST00_RECALL.md` | HISTORICAL FOUNDATION | **wysoka historycznie** | przeniesiony do `docs/archive/plans/v16/` |
| `JAZN_V16_3_22_ACTIVE_RUNTIME_SUBJECT_ROOT_IMPLEMENTATION_PLAN.md` | COMPLETED | **wysoka historycznie** | przeniesiony do `docs/archive/plans/v16/` |
| `JAZN_V16_3_23_PERSISTENT_RUNTIME_LIFECYCLE_OBSERVABILITY_IMPLEMENTATION_PLAN.md` | COMPLETED | **wysoka historycznie** | przeniesiony do `docs/archive/plans/v16/` |
| `JAZN_V15_4_0_0_COGNITIVE_ARCHITECTURE.md` | HISTORICAL | **dobry fundament** | przeniesiony do `docs/archive/plans/v15/` |
| `JAZN_V15_4_2_0_REST_REPLAY_DREAM_CONTINUITY.md` | HISTORICAL | **bardzo dobry truth boundary** | przeniesiony do `docs/archive/plans/v15/` |
| `JAZN_V15_4_2_1_COGNITIVE_TRUTH_MEMORY_INTEGRATION_HARDENING.md` | HISTORICAL | **bardzo wysoka wartość metodologiczna** | przeniesiony do archiwum; evidence ladder promowany do canonical assumptions |
| `JAZN_V15_5_LOCAL_FIRST_MEMORY_CLOUD.md` | HISTORICAL/REFERENCE | **wysoka** | przeniesiony do `docs/archive/plans/v15/`; bieżący cloud/attach contract ma pierwszeństwo |
| `CHATGPT_HOST_FINALIZATION_PROTOCOL_TEST_MATRIX.md` | REFERENCE | **wiarygodna macierz**, ale nie plan | przeniesiony do `docs/runtime/` |

---

# 4. Co zostało zachowane z historycznych planów

## 4.1 Z v15.4.0.0

- dialogue task state;
- retrieval jako evidence, nie identity;
- reasoning lane;
- host-finalized continuity;
- brak ukrytego CoT w durable state.

## 4.2 Z v15.4.2.0

- synthetic Dream ≠ factual memory;
- local-only autonomous dream provider;
- no tools;
- no auto L3;
- shadow-mode first;
- source-grounded replay;
- wake report i hash verification.

## 4.3 Z v15.4.2.1

Promowane do wspólnego kontraktu:

```text
present
constructible
callable
reachable_from_turn
effect_observed
persistence_verified
live_verified
```

To jest najważniejsza metodologiczna lekcja starego planu: **capability nie działa dlatego, że istnieje plik.**

## 4.4 Z v15.5

- local-first memory;
- cloud jako durability/transport, nie aktywny SQLite filesystem;
- local transaction truth boundary;
- verified staging restore;
- cloud failure ≠ local memory failure.

## 4.5 Z v16.3.14

- Test00 → Final;
- source fidelity przed benchmarkiem;
- false-memory/abstention/provenance jako metryki Recall;
- prywatny Test04 ≠ CI.

## 4.6 Z v16.3.22–23

- requested root ≠ subject root;
- runtime identity jako warunek continuity;
- host must route through runtime before conversational output;
- finalization nie może być pominięta;
- persistence/transport claims wymagają realnego evidence.

---

# 5. Research check — zgodność z literaturą

## Autobiographical memory

Conway & Pleydell-Pearce (2000) opisują wspomnienia autobiograficzne jako konstrukcje w Self-Memory System zależne od autobiograficznej bazy wiedzy i bieżących celów working self.

Wniosek dla Jaźni:

- memory retrieval nie musi oznaczać 1:1 odczytu jednego rekordu;
- ale provenance i source conflict muszą pozostać jawne.

Źródło: https://pubmed.ncbi.nlm.nih.gov/10789197/

## Source monitoring

Johnson, Hashtroudi & Lindsay (1993) pokazują, że przypisanie informacji do właściwego źródła jest osobnym, zawodnym procesem pamięciowym.

Wniosek:

- Recall quality musi mierzyć source discrimination, nie tylko trafienie treści.

Źródło: https://pubmed.ncbi.nlm.nih.gov/8346328/

## Emotion / feeling

Scherer & Moors (2019) rozdzielają appraisal/component differentiation od świadomej reprezentacji/experience określanej jako feeling i późniejszego etykietowania.

Wniosek:

- software może wiarygodnie modelować appraisal/regulatory state;
- nazwa `feeling` w Jaźni wymaga jawnej funkcjonalnej definicji i nie może implikować ludzkiej fizjologii/qualiów.

Źródło: https://doi.org/10.1146/annurev-psych-122216-011854

## Metacognition / confidence

Fleming (2024) opisuje confidence jako inferencyjny sąd, który może odbiegać od wykonania.

Wniosek:

- heurystyczne 0.82 nie jest automatycznie „82% prawdopodobieństwa prawdy”.

Źródło: https://doi.org/10.1146/annurev-psych-022423-032425

## Long-term memory benchmarks

LongMemEval mierzy pięć osi: extraction, multi-session reasoning, knowledge updates, temporal reasoning i abstention.

Wniosek:

- prywatny Recall Jaźni powinien obejmować te osie oraz dodatkowo source-discrimination/false-memory/provenance wynikające z charakteru autobiograficznego projektu.

Źródła:
- https://arxiv.org/abs/2410.10813
- https://github.com/xiaowu0162/LongMemEval

## Cognitive modules / ablation

Generative Agents używały ablation do sprawdzenia wkładu observation/reflection/planning.

Wniosek:

- obecność modułu affect/homeostasis/rest/identity dynamics nie wystarcza; przed v17 warto mieć influence/ablation registry.

Źródło: https://arxiv.org/abs/2304.03442

---

# 6. Branch `update/memory-rebuild-v4-roadmap-issues-sync`

Stan przy audycie:

```text
branch HEAD = 03f5427106039970c08cce36336af4ce3eb11863
master      = 5e86793b1fff9ce6f7cbc6b435652681f6c207e5
compare(master...branch): ahead 0 / behind 16
merge-base = branch HEAD
```

Wniosek:

- branch **nie zawiera żadnego unikalnego commita względem master**;
- jego cała praca została już włączona do historii master;
- nie jest źródłem bieżącej roadmapy;
- klasyfikacja: `SUPERSEDED / FULLY MERGED / STALE BRANCH`;
- nie należy z niego rozpoczynać dalszej pracy ani mergować go ponownie.

Branch może zostać później usunięty jako porządek administracyjny, ale ten audyt nie traktuje samego istnienia starego ref jako błędu systemowego.

---

# 7. Najważniejsze korekty planistyczne

1. Jeden kanoniczny assumptions/scientific-boundary contract.
2. Historical plans fizycznie poza aktywnym `docs/plans/`.
3. Finalization matrix poza folderem planów.
4. `emotion` i `feeling` rozdzielone semantycznie.
5. Capability evidence ladder obowiązuje wszystkie nowe plany.
6. Causal continuity ma pierwszeństwo przed linguistic persona.
7. Source monitoring i anti-self-amplification są twardym memory invariant.
8. Affect musi mieć mierzalny downstream influence albo status advisory.
9. Neuro-terminologia pozostaje analogią funkcjonalną.
10. v17 zaczyna się od konsolidacji na podstawie pomiarów, nie od nowych nazw modułów.

---

# 8. GO/STOP dla obecnego release train

## GO

Bieżąca kolejność jest logicznie spójna:

```text
16.3.25.4 Memory Rebuild v4
-> 16.3.26 attachment ingress
-> 16.4.x evidence-aware Polish NLP
-> 16.5.0 VERIFIED final memory
-> 16.5.1 ATTACHABLE
-> 16.5.2+ autobiographical RETRIEVABLE
-> 16.5.y causal continuity / ACCEPTED candidate
-> 16.6 final convergence
-> v17 measured consolidation
```

## STOP conditions

Nie przechodzić dalej, jeżeli:

- derived source może udawać primary;
- final memory nie ma source lineage;
- continuity PASS zależy głównie od stylu pierwszej osoby;
- affective module jest uznany za krytyczny bez behavioral effect evidence;
- confidence jest prezentowane probabilistycznie bez kalibracji;
- Dream/Rest może podnieść false-memory bez gate;
- aktywna roadmapa jest nadpisywana przez historyczny plan;
- P0/P1 truth/integrity pozostaje otwarte.

---

# 9. Granica audytu

Audyt nie oznacza, że wszystkie wymagania są już zaimplementowane. Rozróżnia:

- `credible design`;
- `implemented`;
- `behaviorally verified`;
- `live verified`.

Aktualne statusy wykonawcze nadal wynikają z kodu, testów, raportów release, GitHub CI i zweryfikowanego lokalnego runtime — nie z samego dokumentu planu.
