# Jaźń v16.3.25.5.103 — generative dialogue / NLG convergence

## Cel

Ta aktualizacja usuwa zaobserwowany przypadek, w którym źródłowo poprawny
`MemoryExperienceRecallHandler` stawał się jednocześnie generatorem widocznej,
sztywnej wypowiedzi. Retrieval i provenance pozostają własnością runtime, ale
naturalne sformułowanie odpowiedzi ma przechodzić przez istniejący
`ModelGuidedResponseSynthesizer` albo przez dwufazowy ChatGPT host bridge.

Zmiana nie dowodzi świadomości fenomenalnej ani biologicznych emocji. „Rozumienie
własnej wypowiedzi” w tej wersji oznacza operacyjnie: analizę bieżącej intencji,
kontrolowany kontekst, generację kandydata, sprawdzenie pokrycia semantycznego,
truth/provenance gate oraz finalizację zaakceptowanego tekstu.

## Najważniejszy wniosek z audytu

Repozytorium nie wymaga budowania RAG/NLG od zera. Już istnieją:

- `ModelGuidedResponseSynthesizer`;
- `NlgPlan` i `ModelContextPacket`;
- allowlista `allowed_memory_items`;
- deklarowane `used_memory_item_ids`;
- `HostResponseCandidateGuard`;
- `RuntimeAnswerValidator`;
- `TurnLogicAuditor` i `ReasoningController`;
- dwufazowa finalizacja ChatGPT host bridge.

Błąd polegał na tym, że pamięciowy handler był traktowany jako
`DEDICATED_PRESERVE_HANDLER`, a jego kompletne technicznie body mogło zakończyć
turę bez językowej realizacji model-guided.

## P0 — generatywna realizacja pamięci

`MemoryExperienceRecallHandler`:

1. nadal filtruje i zamraża źródłowo uziemione rekordy;
2. nadal zwraca `memory_sources` do provenance;
3. nie recytuje użytkownikowi ścieżek SQLite ani listy rekordów;
4. deklaruje `requires_model_language_realization=true`;
5. deklaruje `memory_evidence_role=generation_context_not_visible_answer`;
6. nie może być zachowany jako finalny `preserve_handler_body`.

`engine.py` respektuje nowy kontrakt. Handler wymagający językowej realizacji
nie może przejść przez ChatGPT host bridge jako gotowy tekst. Przy lokalnym
adapterze kandydat generuje się model-guided; przy ChatGPT host bridge runtime
żąda fazy host generation/finalization; przy braku kanału językowego zachowanie
pozostaje fail-closed zamiast udawania naturalnej wypowiedzi.

## P0 — semantic coverage

`RuntimeAnswerValidator` wymaga teraz szczegółowego component coverage zawsze,
gdy `analyse_utterance()` rozpozna semantycznie złożoną wypowiedź — nie tylko
wtedy, gdy primary classifier nadał etykietę `compound_dialogue_question`.

Przykład regresji: „Co pamiętasz z naszych rozmów i co czujesz teraz?”
Odpowiedź pokrywająca wyłącznie `memory_recall` nie może już przejść, jeśli
brakuje `self_affect`. Dozwolone jest pełne pokrycie albo jawny evidence gap.

## P1 — routing NLP/NLG capability

Pytania jawnie dotyczące działania lub wystarczalności NLP/NLG/model adaptera
otrzymują `system_diagnostic_question` / `language_architecture` zamiast spadać
do `ordinary_conversation`. To jest diagnostyka architektury i capability; nie
daje prawa do ujawniania prywatnego chain-of-thought.

## P1 — kontrakt naturalnej wypowiedzi

Kontekst modelowy oraz kontrakt host generation mówią teraz wprost:

- memory evidence jest kontekstem generacji, nie gotowym wordingiem;
- każdy wykryty komponent pytania musi być pokryty albo mieć evidence gap;
- raw `source_locator`, ścieżki baz i techniczne identyfikatory nie są pokazywane
  bez jawnej prośby o provenance;
- timestamp pozostaje odpowiedzialnością runtime;
- model językowy nie jest źródłem tożsamości ani pamięci.

## NLP enhanced — świadomie odłożone

Raport badawczy rekomenduje Stanza/spaCy dla polskiej morfologii, dependency
parse i NER. Ta wersja nie dodaje ciężkich zależności runtime, ponieważ główny
zaobserwowany błąd leżał w routingu NLG, nie w samym tokenizatorze. Repozytorium
wymaga osobnego sprawdzenia wersji Pythona, Windows/Linux, wheelhouse/offline
install, czasu startu, pamięci oraz zachowania bez pobierania modeli z sieci
podczas tury. Stanza/spaCy powinny wejść jako osobny opcjonalny `nlp_enhanced`
patch po benchmarku względem obecnego `nlp_core`, a nie jako warunek rdzenia.

## Kryteria akceptacji

1. Memory handler nie przechodzi bezpośrednio przez host bridge, jeśli wymaga
   model language realization.
2. Uziemione `memory_sources` pozostają dostępne dla provenance/finalizera.
3. Naturalna odpowiedź pamięciowa nie musi ujawniać raw database path.
4. Semantycznie wielointencyjne pytanie jest fail-closed przy brakującym
   komponencie.
5. Pytanie o NLP/NLG capability nie spada do ordinary fallback.
6. Istniejące truth, identity, provenance i autobiographical readiness gates
   nie są osłabiane.

## Test regresji

Nowy plik `tests/test_v163255103_generative_dialogue_nlg_convergence.py` sprawdza:

- kontrakt evidence-only pamięci;
- blokadę bezpośredniego pass-through przez ChatGPT host bridge;
- wymuszenie `memory_recall + self_affect` coverage;
- techniczny routing pytania o NLP.

## Walidacja

Executor hosta był niedostępny podczas przygotowywania patcha, więc lokalne
`pytest`, `compileall` i `pyright` nie są raportowane jako wykonane. Po zapisie
brancha źródłem prawdy dla weryfikacji jest GitHub Actions. Ewentualne regresje
należy naprawiać bez osłabiania testów ani truth gate.
