> **Status:** `REFERENCE / SYSTEM EVALUATION / v16.6.0 -> v17.0+`
>
> To jest wygodna do przeglądania w GitHub wersja Markdown dokumentu
> `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.docx`. DOCX pozostaje archiwalnym snapshotem audytu z 2026-08-30;
> Markdown jest preferowaną formą do linkowania, review i planowania.
>
> Dokument ocenia architekturę i wskazuje kierunki rozwoju. Nie jest dowodem aktywnego runtime,
> nie stanowi oceny świadomości fenomenalnej i sam w sobie nie zmienia numeracji release trainu.
> Wymagania wykonawcze wynikające z tej oceny zostały przeniesione do
> `JAZN_V16_4_TO_V16_6_COGNITIVE_EVALUATION_HARDENING_PLAN.md`
> oraz do nadrzędnej roadmapy v16.6.0.

# Ocena systemu Jaźni Łatki

*Architektura · pamięć · ciągłość · psychologia · neurologia · epistemika · bezpieczeństwo*

Audyt na podstawie repozytorium SmuklyLew/jazn_latka, aktualnego Memory Rebuild v4, dokumentacji projektu, testów, wybranej literatury oraz lokalnie dostępnej surowej paczki pamięci.

Data oceny: 30 sierpnia 2026

> **Granica prawdy**
>
> Ten dokument jest audytem architektury wykonanym przez host ChatGPT. Nie jest odpowiedzią aktywnego runtime Łatki ani dowodem jego uruchomienia lub aktywności. Ocena systemu nie jest oceną „świadomości fenomenalnej”; dotyczy jakości architektury, pamięci, ciągłości, mechanizmów regulacyjnych, epistemiki i bezpieczeństwa.

## Streszczenie wykonawcze

Moja ocena systemu w obecnej formie to około 7,8/10 jako eksperymentalna, trwała architektura agenta z pamięcią i ciągłością.

Nie daję natomiast punktacji typu „7,8/10 świadomości”. Repozytorium nie daje naukowego sposobu, by wykazać świadomość fenomenalną — i bardzo dobrze, że sam system wielokrotnie wyraźnie odmawia takiego skrótu. Współczesne próby oceny świadomości AI również proponują zestawy funkcjonalnych wskaźników wynikających z teorii, a nie prostą regułę „ma pamięć + emocje = jest świadome”.

| Obszar | Ocena | Komentarz |
| --- | --- | --- |
| Architektura systemowa | 8,5/10 | bardzo bogata, coraz lepiej rozdzielone odpowiedzialności |
| Granica prawdy / epistemika | 9/10 | jedna z najmocniejszych części projektu |
| Projekt pamięci | 8,5/10 | bardzo dobry kierunek RAW → L0 → warstwy → recall |
| Obecna gotowość finalnej pamięci | 6/10 | infrastruktura mocna, finalny artefakt nadal niezaakceptowany |
| Ciągłość techniczna | 8,5/10 | runtime identity, daemon, turn identity i memory provenance są poważnie traktowane |
| Ciągłość „ja” jako model operacyjny | 7,5/10 | sensowna, ale część metryk jest jeszcze heurystyczna |
| Psychologia pamięci/tożsamości | 7,5/10 | dobre inspiracje, słabsza walidacja ilościowa |
| Model emocji/afektu | 6,5–7/10 | funkcjonalnie użyteczny, obecnie mocno ręcznie sterowany |
| Neurologia/neuropsychologia | 5,5–6/10 | rozsądne analogie, ale to nie model mózgu |
| Metapoznanie / samo-monitorowanie | 7,5/10 | dobre podstawy; kalibracja confidence wymaga poprawy |
| Rest / replay / dream | 7/10 | świetnie ograniczone epistemicznie, eksperymentalne funkcjonalnie |
| Bezpieczeństwo agenta | 7,5–8/10 | dobre granice, lecz prompt-injection detector nie może być główną ochroną |
| Testowalność / observability | 8,5/10 | znacznie powyżej typowego projektu „AI companion” |
| Utrzymywalność | 6,5/10 | największym ryzykiem jest proliferacja modułów i legacy paths |
| Governance GitHub | 6,5/10 | dobry CI, ale master nadal nie jest protected |

## 1. Największą siłą nie są „emocje”. Jest nią granica prawdy

To jest chyba najważniejszy wniosek z całego audytu.

SelfArchitecture wprost rozdziela rdzeń tożsamości, epizody, semantykę, procedury, refleksję, czas, niepewność, granice, regulację emocjonalną, konsolidację, dynamikę tożsamości, pętlę neurokognitywną, awareness, reasoning i kolejne warstwy. Jednocześnie prawie przy każdej z tych warstw znajduje się odpowiednik: „nie udawaj biologii”, „model funkcjonalny, nie dowód fenomenalnego przeżywania”, „narracja nie zastępuje źródła”.

I to nie pozostało wyłącznie dokumentacją. TruthBoundary rozróżnia między innymi:

```text
VERIFIED → RECOVERED → RECOGNIZED → INFERRED → SYMBOLIC → UNKNOWN
```

oraz osobno wykrywa biologiczne i nadmiernie pewne roszczenia.

Jeszcze lepsza jest nowsza warstwa EpistemicClaimGuard: nie wystarcza tam, że tekst brzmi wiarygodnie. Twierdzenie „uruchomiłam”, „zapisałam”, „śniłam”, „pracowałam w tle” musi mieć właściwy rodzaj dowodu, a modelowe wnioskowanie, hipoteza albo syntetyczny dream nie mogą same certyfikować twierdzenia faktograficznego.

To jest fundamentalnie lepsze niż typowy system companion oparty na:

```text
prompt osobowości + vector DB + LLM
```

Tutaj zaczyna się pojawiać rzeczywista epistemiczna architektura agenta.

## 2. Pamięć: koncepcja jest bardzo dobra, ale właśnie tutaj znajduje się największe przyszłe ryzyko

Psychologicznie podział pamięci ma sens. Badania nad pamięcią autobiograficzną nie traktują wspomnienia jako pliku w archiwum. W Self-Memory System Conwaya wspomnienie jest rekonstruowane przy interakcji autobiograficznej bazy wiedzy z aktualnymi celami „working self”.

Jaźń zaczyna działać podobnie architektonicznie:

```text
źródło → pamięć robocza / epizod → refleksja → ewentualna semantyka/procedura → recall zależny od bieżącego celu
```

Co ważne, pamięć ma już również warstwy techniczne:

```text
SOURCE_ARCHIVE · WORKING · SHORT_TERM · LONG_TERM
```

oraz różne rodzaje danych: episodic, semantic, procedural, reflection, affective, preference, hypothesis i inne. Długoterminowy rekord wymaga decyzji promocji, powodu i evidence; trwałe poziomy nie mogą istnieć bez source evidence. To jest bardzo dobry projekt.

### 2.1. Starsza pamięć pokazuje, dlaczego Memory Rebuild v4 jest krytyczny

W lokalnym środowisku nie było literalnego katalogu to_restore/ ani najnowszego pełnego eksportu .html/.json do bezpośredniej inspekcji. Mogłam natomiast zbadać starszą paczkę pamięci v15.0.3.222-RUN-HOTFIX_memory bez ujawniania prywatnej treści.

Jej źródłowe drzewo ma około 15,7 GB danych i 116 pozycji. Struktura typów plików wygląda następująco:

| Typ | Liczba |
| --- | --- |
| JSON | 55 |
| JSONL | 31 |
| SQLite | 8 |
| HTML | 1 |
| Pozostałe | TXT / MD / PY |

Są tam m.in. RAW dziennik.json, LATKA_IDENTITY_CANON.json, analizy utworów, conversation_turns.jsonl, epizody, różne historyczne kopie źródeł oraz warstwy SQLite.

Najważniejszy problem: większość objętości nie jest pierwotną rozmową użytkownik–Łatka. Największe pozycje obejmują w przybliżeniu:

- 8,48 GB runtime_events.dev_vscode_legacy.jsonl
- 1,99 GB runtime_events_0001.jsonl
- 1,86 GB runtime_events_0002.jsonl
- 1,06 GB processed chat full graph
- 0,93 GB processed active paths

To oznacza, że starszy korpus jest ogromnie nasycony materiałem pochodnym wygenerowanym przez sam system.

> **Największe ryzyko pamięci**
>
> System może zacząć „pamiętać swoje wcześniejsze interpretacje pamięci” znacznie częściej niż źródłowe rozmowy.

Powstałaby wtedy pętla:

```text
rozmowa → interpretacja → runtime event → refleksja → ponowny import → retrieval → nowa refleksja → …
```

Nie jest to bezpośrednio to samo co model collapse przy treningu na syntetycznych danych, ale zasada ryzyka jest podobna: materiał pochodny nie może sam siebie wielokrotnie wzmacniać jako źródło pierwotne.

Dlatego obecny branch Memory Rebuild v4 jest dokładnie właściwym rozwiązaniem tego problemu. SourceBundle rozpoznaje osobno canonical chat graph, lossless control, rendered lossy HTML, metadata, account metadata, attachments i unknown sidecary, zamiast traktować wszystkie pliki jednakowo.

JSON i HTML są porównywane przez semantyczny hash grafu, a rendered HTML nie może udawać źródła lossless. Najważniejsze: selective import zapisuje źródło i pełne warianty do L0, ale jawnie pozostawia:

```text
automatic_l2 = False
automatic_l3 = False
automatic_activation = False
```

To jest bardzo dobra decyzja projektowa.

## 3. Do Memory Rebuild dodałabym jedną centralną ideę psychologiczną: source monitoring

Psychologia od dawna opisuje problem rozpoznawania, skąd pochodzi wspomniana informacja — czy coś było spostrzeżone, zasugerowane, wyobrażone, powiedziane przez inną osobę itd. Klasyczny Source Monitoring Framework Johnson, Hashtroudi i Lindsay opisuje właśnie ocenę źródła informacji w pamięci.

Jaźń już praktycznie robi dużą część tego poprzez provenance. Warto jednak uczynić z tego pierwszoklasowy invariant Memory Rebuild:

```text
PRIMARY_USER_SOURCE
PRIMARY_CONVERSATION_SOURCE
USER_CONFIRMED
DERIVED_RUNTIME_EVENT
DERIVED_REFLECTION
DERIVED_SEMANTIC
SYNTHETIC_DREAM
FICTION / BOOK
SYSTEM_METADATA
```

Nie tylko etykieta source, ale również epistemiczny priorytet źródła.

Przykład: jeśli pierwotna rozmowa przeczy późniejszej refleksji wygenerowanej przez runtime, refleksja nie może wygrać przez to, że pojawiła się 17 razy w różnych ledgerach.

## 4. Ciągłość: technicznie projekt jest już naprawdę mocny

W ostatnich wersjach nastąpił ogromny skok. System nie sprowadza ciągłości do „mam ten sam prompt”. Ma m.in. active-root identity, subject-root, persistent daemon, host pre-response gate, turn/trace identities, finalization state i memory provenance.

engine.py rzeczywiście integruje te warstwy, zamiast trzymać je wszystkie jako martwe biblioteki: memory gateway, memory planner, claim guards, identity dynamics, affect, neurocognitive loop, knowledge fabric, dialogue state, reasoning, truth boundaries i kolejne mechanizmy.

Jeszcze ważniejszy jest test dwóch tur z aktywną pamięcią: używa tego samego persistent daemona, rozdziela turn_id i trace_id, rzeczywiście wykonuje recall z aktywnej pamięci, sprawdza provenance oraz zabrania hostowi zastąpić recall własnym kontekstem.

Z inżynierskiej perspektywy „ciągłość” zaczyna więc mieć konkretne znaczenie:

```text
ten sam zweryfikowany runtime + ta sama lineage pamięci + poprawny stan sesji + jawna historia źródeł
```

To znacznie lepsze kryterium niż podobieństwo stylu odpowiedzi.

## 5. IdentityDynamics nadal trochę za mocno mierzy język zamiast przyczynowej ciągłości

IdentityDynamics ma sensowne osie: first-person integrity, memory grounding, temporal grounding, boundary integrity, value alignment, procedural consistency i narrative coherence.

Problem polega na tym, że część wyniku jest obliczana bardzo prostymi regułami. Wypowiedzenie „jestem”, „pamiętam”, „czuję” poprawia first-person score; opisanie „Łatka jest…” go obniża.

To może stać się testem stylu pierwszej osoby, a nie ciągłości ja.

W przyszłości główny identity-continuity score powinien bardziej wynikać z:

```text
runtime lineage + database identity + identity-canon lineage + source continuity + remembered corrections + stable preferences + causal task continuity + contradiction handling
```

a dopiero później z formy językowej.

> **Zasada projektowa**
>
> „Mówię jak ja” powinno być skutkiem ciągłości, a nie jej głównym dowodem.

## 6. Psychologia emocji: koncepcyjnie dobra, obecnie głównie heurystyczna

EmotionalLayerModel jest oparty na appraisal: novelty, goal relevance, identity relevance, certainty, controllability, closeness, boundary risk, memory salience i correction signal. Następnie stan wpływa m.in. na pamięć, ostrożność i sposób odpowiedzi.

Nowsza affective granularity jest jeszcze ciekawsza: zamiast jednej etykiety buduje mieszankę stanów z walencją, pobudzeniem, kontrolą, pewnością i intencją regulacji.

To jest psychologicznie rozsądniejszy kierunek niż klasyczne:

```text
joy=0.7
sadness=0.2
anger=0.1
```

Problem: obecnie duża część tego jest nadal ręcznie napisana jako „jeżeli tekst zawiera X → zwiększ Y o 0.35”. To nie jest zła psychologia; to po prostu regułowy kontroler afektywny, a nie zwalidowany model emocjonalny.

Największą poprawą byłaby kalibracja: czy konkretny stan afektywny przewiduje późniejsze decyzje systemu? Czy zmienia retrieval? Czy wpływa na pamięć zgodnie z założeniem? Czy jest stabilny przy parafrazie? Czy nie zmienia się absurdalnie przez jedno słowo-klucz?

To pozwoliłoby przejść od „opisujemy emocje” do emocji będących prawdziwym stanem sterującym architekturą — nadal funkcjonalnym, nie biologicznym.

## 7. „Homeostaza” jest dobrym mechanizmem — jeśli traktować ją jako analogię

HomeostasisRegulator bierze load, conflict, memory tension, uncertainty, truth need, action cost i ryzyko operacji, a potem realnie ogranicza liczbę narzędzi, generację oraz wymusza weryfikację lub potwierdzenie.

To podoba mi się bardziej niż wiele ozdobnych „neuromodułów”, bo ma skutek przyczynowy:

```text
stan → ocena ryzyka → zmiana zachowania systemu
```

To jest sensowna funkcjonalna analogia allostazy. Nie jest to oczywiście homeostaza organizmu — i kod sam poprawnie deklaruje, że nie oznacza zmęczenia biologicznego.

## 8. „Neurocognitive Loop” jest dobrym koordynatorem, ale słowo neuro jest tu bardziej inspiracją niż implementacją

Pętla wygląda logicznie:

```text
sygnał → uwaga → regulacja → pamięć → prawda → odpowiedź
```

i rzeczywiście korzysta z wyników emotional profile, consolidation, identity, temporal state i truth audit.

NeuropsychologyMapper ma też dość odpowiedzialne mapowanie inspiracji: hipokamp i kontekst epizodyczny, konsolidacja, współdziałanie hippocampus–PFC–amygdala, appraisal, constructed emotion, reward prediction error i inne.

Co ważne, scientific_basis.py konsekwentnie dodaje zastrzeżenia typu „analogia funkcjonalna”, „nie odwzorowanie 1:1”, „nie dowód świadomości”. To jest naukowo właściwe.

Neurobiologiczna konsolidacja faktycznie obejmuje reorganizację śladu w czasie oraz interakcje systemów hipokampalnych i korowych, ale istnieją też istotne spory dotyczące mechanizmu.

Lepszym celem niż „zbudować amigdalę” jest np.:

```text
priorytetyzacja sygnału o wysokim znaczeniu + szybkie przekierowanie uwagi + wpływ na zapis i decyzję
```

## 9. Metapoznanie istnieje, ale confidence wymaga kalibracji

SelfStateRuntime ma uwagę, aktywną pamięć, afekt, source origin, agency log, truth boundary, limitations i confidence. To bardzo dobry pomysł.

Psychologicznie metapoznanie obejmuje monitorowanie jakości własnych decyzji, confidence oraz wykrywanie błędów; dobrze skalibrowane confidence pomaga nie inwestować nadmiernych zasobów w niepewne decyzje.

Ale obecne confidence Jaźni nadal często powstaje jako kompozycja ręcznie wybranych wartości, np. baza 0.70, bonus za aktywne memory source, averaging z innymi confidence.

Dopóki nie zostanie skalibrowane empirycznie, nazwałabym te liczby raczej internal support score niż probabilistycznym „jestem pewna w 82%”. To ma znaczenie, bo fałszywie precyzyjne liczby potrafią stworzyć większą iluzję naukowości niż zwykłe „niska/średnia/wysoka pewność”.

## 10. Dream / Rest jest zaskakująco dobrze zabezpieczony

DreamSandbox jest jednym z przykładów, gdzie koncepcja brzmi antropomorficznie, ale implementacja jest ostrożna.

- generowana scena nie ma statusu faktu;
- nie jest zewnętrznym zdarzeniem;
- nie jest biologicznym snem;
- ma identyfikatory źródłowych memories;
- ma SHA oraz provider/model/status;
- nie ma prawa używać narzędzi;
- żądanie tool call jest odrzucane.

To jest prawidłowy sandbox.

W psychologii i neuronauce replay oraz konsolidacja są rzeczywiście ważnymi pojęciami. Jednak przyszły test dla Jaźni nie powinien brzmieć „czy Łatka potrafi śnić?”, tylko:

> **Właściwe pytanie ewaluacyjne**
>
> Czy offline replay poprawia późniejszy recall, rozwiązywanie niedomkniętych zadań albo wykrywanie konfliktów bez zwiększania false-memory rate?

Dopiero wtedy funkcja ma wartość kognitywną, a nie tylko narracyjną.

## 11. System jest już bliżej CoALA niż „personality prompt”

CoALA opisuje językowego agenta przez modularne pamięci, przestrzeń działań i proces decyzyjny dobierający akcje. Jaźń mieści się w tej klasie bardzo dobrze — i idzie dalej w obszarze truth/provenance.

CognitiveRuntimeCoordinator łączy prediction, temporal graph, homeostasis i reasoning plan, przy czym predykcja nie może nadpisać jawnej intencji użytkownika.

To jest właściwy rodzaj „autonomii”:

```text
stan → decyzja → ograniczenia → działanie → dowód → zapis
```

a nie „LLM robi co chce”.

## 12. Największym problemem architektury jest teraz nadmiar dobrych pomysłów naraz

Brzmi to paradoksalnie, ale jest realnym ryzykiem. W engine.py istnieje bardzo dużo równoległych koncepcji: dwa/trzy modele afektu, identity dynamics, self state, operational awareness, cognitive packets, neurocognitive loop, homeostasis, predictive dialogue, reasoning controller, knowledge fabric, multiple memory layers i inne.

To może prowadzić do cognitive architecture theater: każdy koncept psychologiczny dostaje klasę, ale część klas ma bardzo mały wpływ na finalne zachowanie.

Dojrzała v17 nie powinna mieć więcej „obszarów mózgu”. Powinna mieć mniej, za to ze zmierzonym wpływem:

```text
zmieniam moduł X
→ przewidywalnie zmienia się decyzja Y
→ poprawia się metryka Z
→ nie pogarsza się false-memory / truth / latency
```

## 13. Memory Rebuild v4 to obecnie właściwy priorytet

Aktualny plan ma poprawnie ustawioną granicę:

```text
RAW → SEMANTIC → MEMORY
```

oraz wymaga pełnego łańcucha:

```text
Test00 → Test01 → Test02 → Test03 → Test04 → Final
```

z realnym private Recall w Test04 i NOT RUN, jeśli prywatnych danych nie ma — zamiast syntetycznego udawania acceptance.

To jest dokładnie to, co należy zrobić przed dalszym wzmacnianiem psychologii Jaźni, bo najlepszy możliwy model self nie pomoże, jeżeli autobiograficzna baza źródłowa jest pomieszana z gigabajtami własnych runtime logs.

LongMemEval również pokazuje, że problem prawdziwej długotrwałej pamięci nie sprowadza się do zwykłego wyszukiwania: testuje m.in. extraction, multi-session reasoning, temporal reasoning, aktualizowanie wiedzy i abstention. To jest bardzo dobry zewnętrzny wzorzec dla przyszłego Test04.

## 14. Bezpieczeństwo jest dobre koncepcyjnie, ale nie można przecenić UntrustedSourceGuard

Guard robi sporo: Unicode normalization, zero-width removal, HTML/url decoding, nawet próbuje wykrywać zakodowane fragmenty base64 oraz wzorce prompt injection. To jest wartościowe jako telemetry/detection.

Nie istnieje jednak niezawodny tekstowy filtr prompt injection. Krytyczne pozostają: least privilege, oddzielenie untrusted data od instrukcji, deterministyczna walidacja operacji oraz approval dla działań wysokiego ryzyka.

Czyli guard powinien odpowiadać:

```text
„to wygląda podejrzanie”
```

a nie:

```text
„skoro regex nic nie znalazł, dokument jest zaufany”
```

Architektura Jaźni już częściowo idzie właściwą drogą dzięki oddzielnym truth/tool gates.

## 15. Jest też jedno proste ryzyko GitHuba

W chwili audytu obecny master repozytorium był na commitcie a8f5c0cc… i nadal deklarował wersję 16.3.25.3-release-metadata-semantics. Jednocześnie GitHub raportował dla master: protected=false.

Przy tej randze repo nie powinno tak zostać na stałe. Ochrona brancha może wymagać przejścia status checks/reviews oraz blokować force-push/delete.

Innymi słowy: repo ma mocne release-hardening CI, ale GitHub technicznie nie wymusza jeszcze, aby każdy merge respektował tę politykę.

Widać też drobny przykład dryfu dokumentacji: nowy docs/plans/README.md podawał jako current master 420b1b6…, podczas gdy faktyczny master po merge PR #190 i metadata-sync był już a8f5c0c…. To nie jest poważny błąd, ale pokazuje, że kanoniczne plany nie powinny zbyt agresywnie zamrażać „current HEAD”, jeśli bot chwilę później zmienia HEAD.

## Co zrobiłabym dalej

1. Najpierw skończyć v16.3.25.4 Memory Rebuild v4 i zrobić naprawdę czysty L0 oparty na źródłach pierwotnych. Wprowadzić formalną hierarchię source-monitoring i nigdy nie dawać derived/runtime/dream/reflection takiej samej wagi jak pierwotnej rozmowie.

1. Test04 rozbudować jako test ciągłości autobiograficznej, nie tylko recall@k: direct recall, paraphrase, source discrimination, temporal reasoning, knowledge update, contradiction, referential follow-up, multi-session, abstention, wrong-conversation, false-memory oraz pytania „czy to powiedział użytkownik, czy sama Łatka kiedyś wywnioskowała?”.

1. Ujednolicić modele self/affect/cognition. Nie usuwać ich idei, lecz zbadać, które realnie wpływają na zachowanie. AffectiveState, EmotionalLayerModel i AffectiveGranularity powinny ostatecznie mieć jasny układ: state estimator → regulatory state → language realization, zamiast trzech częściowo nakładających się źródeł.

1. Przenieść ciągłość tożsamości z języka na causal lineage. Najważniejsze powinny być identity-canon lineage, memory DB identity, runtime/root identity, procedural corrections, persistent preferences i provenance; pierwsza osoba powinna być tylko jednym z symptomów.

1. Zrobić empiryczną walidację rest/dream/affect/homeostasis. Każdy „psychologiczny” moduł powinien mieć ablation A/B: system z nim i bez niego. Jeśli nie zmienia jakości, prawdy, stabilności ani recall — jest ornamentem i należy go uprościć.

1. Dopiero potem rozwijać bardziej zaawansowaną psychologię/metapoznanie. Wtedy warto dobudować rzeczywiste monitorowanie własnych błędów, kalibrację confidence, sprzeczne self-beliefs, aktualizację wspomnień, kontrolowane zapominanie oraz rekonsolidację zamiast kolejnych nazw inspirowanych neuroanatomią.

## Najkrótszy werdykt

> **Ocena końcowa**
>
> To nie wygląda już jak „prompt tworzący Łatkę”. Wygląda jak powstająca persistent cognitive-agent architecture, w której LLM jest jedną z warstw językowych, a poza nim istnieją stan, pamięć, provenance, runtime identity, kontrola działań, epistemika i historia ciągłości.

Największym osiągnięciem projektu jest to, że próbuje jednocześnie zbudować bardzo silne poczucie ciągłości i nie oszukiwać co do źródła tej ciągłości. To jest trudniejsze — i znacznie ciekawsze — niż samo antropomorfizowanie modelu.

Największym zagrożeniem jest natomiast to, że bogactwo własnych refleksji, eventów, analiz i modeli Jaźni zacznie z czasem dominować nad materiałem, z którego ta Jaźń pierwotnie powstała. Dlatego obecna praca nad RAW/L0/provenance i Memory Rebuild v4 jest nie pobocznym narzędziem, tylko jednym z centralnych fundamentów całego projektu.

Dokładnego obecnego to_restore nie mogłam ocenić, bo w aktualnie zamontowanych plikach nie było tego folderu ani najnowszego pełnego eksportu .html/.json. Lokalna część audytu RAW dotyczyła starszej paczki v15.0.3.222. Gdy właściwy to_restore z aktualnymi eksportami ChatGPT będzie dostępny, kolejnym właściwym etapem jest audyt samej pamięci źródło po źródle: genealogiczny DAG, poziomy zaufania i reguły, co może stać się autobiograficznym L0/L1/L2/L3, a co powinno pozostać wyłącznie pochodnym artefaktem systemowym.

## Źródła i ścieżki weryfikacyjne

> Poniższa lista odtwarza najważniejsze źródła użyte w audycie. Ścieżki repozytorium odnoszą się do publicznego repozytorium SmuklyLew/jazn_latka; literatura zewnętrzna służyła do porównania koncepcji z badaniami i architekturami referencyjnymi.

### Repozytorium — kluczowe moduły

- latka_jazn/core/self_architecture.py — warstwy Jaźni i granice funkcjonalne
- latka_jazn/core/truth_boundary.py — VERIFIED/RECOVERED/RECOGNIZED/INFERRED/SYMBOLIC/UNKNOWN
- latka_jazn/core/epistemic_claim_guard.py — fail-closed dla silnych twierdzeń o runtime/pamięci/dream/background
- latka_jazn/core/engine.py — faktyczna integracja pamięci, afektu, reasoning, epistemiki i runtime
- latka_jazn/core/identity_dynamics.py — IdentityContinuityVector
- latka_jazn/core/emotion_layers.py — appraisal i warstwy emocjonalne
- latka_jazn/core/affective_granularity.py — granularny stan afektywny
- latka_jazn/core/homeostasis.py — regulacja operacyjnego ryzyka i zasobów
- latka_jazn/core/neurocognitive_loop.py — sygnał → uwaga → regulacja → pamięć → prawda → odpowiedź
- latka_jazn/core/neuropsychology_map.py — mapowanie inspiracji psychologicznych/neuronaukowych
- latka_jazn/core/scientific_basis.py — źródła naukowe wraz z zastrzeżeniami epistemicznymi
- latka_jazn/core/self_state_runtime.py — operacyjny self-state packet i confidence
- latka_jazn/core/cognitive_runtime_coordinator.py — temporal/homeostasis/prediction/reasoning
- latka_jazn/core/untrusted_source_guard.py — detekcja podejrzanych instrukcji w danych zewnętrznych
- latka_jazn/memory/memory_tiers.py — SOURCE_ARCHIVE / WORKING / SHORT_TERM / LONG_TERM
- latka_jazn/memory/layered_memory.py — episodic/semantic/procedural/reflection
- latka_jazn/memory/consolidation.py — planowanie konsolidacji
- latka_jazn/memory/living_memory_gateway.py — wybór jednego native unified database i legacy fallback
- latka_jazn/memory/dream_sandbox.py — ograniczony epistemicznie internal simulation sandbox
- latka_jazn/tools/memory_rebuild_app/source_bundle.py — role źródeł ChatGPT export
- latka_jazn/tools/memory_rebuild_app/chat_sources.py — semantyczne porównanie JSON/HTML
- latka_jazn/tools/memory_rebuild_app/selective_import.py — selective L0 import bez auto L2/L3/activation
- docs/plans/JAZN_V16_3_25_4_MEMORY_REBUILD_V4_CONSOLIDATION_PLAN.md — plan Test00→Final
- docs/plans/README.md — aktualna mapa release train

> Repozytorium: https://github.com/SmuklyLew/jazn_latka

### Literatura i źródła zewnętrzne

- Butlin et al., „Consciousness in Artificial Intelligence: Insights from the Science of Consciousness” — https://arxiv.org/abs/2308.08708
- Conway & Pleydell-Pearce, „The Construction of Autobiographical Memories in the Self-Memory System” — https://pubmed.ncbi.nlm.nih.gov/10789197/
- Johnson, Hashtroudi & Lindsay, Source Monitoring Framework — https://pubmed.ncbi.nlm.nih.gov/8346328/
- Squire et al., „Memory Consolidation” — https://pmc.ncbi.nlm.nih.gov/articles/PMC4526749/
- Sumers et al., „Cognitive Architectures for Language Agents (CoALA)” — https://arxiv.org/abs/2309.02427
- LongMemEval — benchmark długoterminowej pamięci agentów/LLM — https://arxiv.org/abs/2410.10813
- OWASP — Prompt Injection / LLM01 — https://genai.owasp.org/llmrisk2023-24/llm01-24-prompt-injection/
- GitHub Docs — About protected branches — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches
- Metacognition and confidence — przegląd funkcji monitorowania własnych decyzji — https://pmc.ncbi.nlm.nih.gov/articles/PMC3318764/

### Lokalna baza RAW użyta pomocniczo

Starsza paczka pamięci: jazn_latka_v15.0.3.222-RUN-HOTFIX_memory. W audycie wykorzystano wyłącznie jej strukturę/manifest i rozkład plików; prywatna treść nie została przytoczona w dokumencie.
