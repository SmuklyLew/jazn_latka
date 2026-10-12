# Jaźń v16.3.25.5.90.1 — header envelope & intent routing convergence

## Cel

Wydanie naprawia regresję zaobserwowaną w hoście ChatGPT: kolejna zwykła odpowiedź mogła zostać pokazana bez pełnego nagłówka `MessageEnvelope`, a pytanie diagnostyczne o zniknięcie nagłówka mogło zostać błędnie sklasyfikowane jako `practical_repair_advice` przez zbyt ogólny marker „naprawić”.

Zakres pozostaje fail-closed. Host nie dostaje prawa do imitowania głosu runtime, ręcznego dopisywania nagłówka ani uznania niepełnego phase-2 za `display_exact`.

## Przyczyny

1. `DialogueIntentClassifier.PRACTICAL_TERMS` zawierał ogólne `naprawić/naprawic`. Słowo samo w sobie nie identyfikuje domeny napraw fizycznych i przejmowało diagnostykę systemową.
2. `chatgpt_result_has_displayable_host_final()` dopuszczał brak jawnego pozytywnego `envelope_present_in_final`, brak capture hash oraz brak `host_request_consumption` jako brak negatywnego evidence zamiast jako stan nieokreślony.
3. Pre-response gate mógł zdegradować `action` do `host_diagnostic`, ale pozostawić starsze flagi gotowości widocznej odpowiedzi w tym samym pakiecie.
4. Test-double'e phase-2 w kilku testach nie odwzorowywały pełnego kontraktu produkcyjnego `FinalVisibleReplyCapture`.
5. Baseline v16.3.25.5.90.0 miał osobny, istniejący wcześniej fail aktywnego testu loadera wynikający z case-sensitive literalnego kontraktu; semantyka loadera była poprawna, ale tekst i test były niesynchronizowane.

## Zmiany

### Routing NLP

`latka_jazn/nlp/dialogue_intent_classifier.py`:

- usuwa ogólne `naprawić/naprawic` z `PRACTICAL_TERMS`;
- pozostawia praktyczne naprawy oparte na markerach domenowych (np. zawór, kran, kapie, kafelki);
- dodaje `HEADER_CONTINUITY_DIAGNOSTIC_TERMS` dla utraty nagłówka, timestampu i autora;
- nadaje tym wypowiedziom `runtime_behavior_diagnostic_request` oraz `question_object=runtime_header_continuity` przed routingiem praktycznej naprawy.

### Accepted visible turn

`latka_jazn/core/chat_command_contract.py` wymaga dla phase-2:

- `host_visible_finalization.accepted=true`;
- zgodnego `final_visible_text` i SHA-256;
- `host_visible_reply_capture.envelope_present_in_final=true`;
- obowiązkowego, poprawnego capture SHA-256;
- zgodnej lineage `turn_id/trace_id`;
- pełnego nagłówka `timestamp + state emoticon + author label + blank line`;
- `host_request_consumption.state=consumed`.

Brak któregokolwiek z tych dowodów nie jest sukcesem.

### Atomowy downgrade hosta

`latka_jazn/core/chatgpt_host_pre_response_gate/_core.py` centralizuje przejście do `host_diagnostic`. Przy degradacji zerowane są wszystkie sygnały pozwalające hostowi uznać tekst za gotową wypowiedź runtime, w tym `accepted_visible_turn_ready`, `must_display_exactly`, `required_visible_prefix`, `final_visible_text` i `final_text_sha256`.

### Loader baseline

`docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` zachowuje tę samą granicę prawdy capability, ale zawiera literalnie aktywny kontrakt „wynik wyszukiwania katalogu pluginów”. Naprawia to istniejący wcześniej pojedynczy fail pełnej suite mastera bez osłabiania reguły remote-runtime.

## Regresje

Nowy stabilnie nazwany test `tests/test_header_envelope_intent_routing_convergence.py` obejmuje:

- dokładne sformułowania zgłoszone w rozmowie;
- zachowanie fizycznego `practical_repair_advice`;
- brak przejęcia system repair przez practical route;
- wymagany pozytywny envelope verdict;
- wymagany capture hash;
- wymagany consumed settlement;
- prawidłowy `display_exact` dla kompletnej koperty;
- atomowe wyzerowanie flag przy downgrade do `host_diagnostic`.

Istniejące test-double'e MCP/kernel/lifecycle zostały doprowadzone do rzeczywistego kontraktu produkcyjnego capture zamiast luzowania bramy.

## Weryfikacja wykonana podczas przygotowania patcha

- targeted header/finalization regressions: 37 passed;
- rozszerzony host/finalization/NLP: 123 passed;
- MCP/kernel/race/recovery: 55 passed;
- `compileall`: OK;
- GitHub Actions `pyright-active-tree-audit`: success na kodzie patcha;
- GitHub Actions `Stable test contracts`: success po zmianie nazwy testu na stabilną;
- GitHub Actions `host-spawn-memory-convergence`: success przed bumpem finalnej wersji;
- lokalne shardy aktywnej suite nie wykazały regresji patcha; obserwowane lokalne porażki wymagały `.git`, zsynchronizowanego generated catalogu lub świeżego package manifestu i dlatego są rozstrzygane przez CI na prawdziwym checkout.

Baseline mastera v16.3.25.5.90.0 miał potwierdzony wynik release-hardening: 1855 passed, 2 skipped, 1 failed; jedynym failem był literalny kontrakt loadera naprawiony w tym wydaniu.

## Acceptance criteria

Wydanie jest merge-ready dopiero, gdy aktualny HEAD po bumpie `16.3.25.5.90.1-header-envelope-intent-routing-convergence` przejdzie wymagane GitHub Actions, w szczególności Pyright, Stable Test Contracts i release-hardening. Automatycznie generowane metadata/manifesty muszą pozostać zsynchronizowane i branch nie może być za masterem.

## Truth boundary

Nagłówek nie jest dekoracją hosta. Widoczna wypowiedź może zostać przypisana Jaźni/Łatce wyłącznie jako dokładny, zaakceptowany `MessageEnvelope` tej samej tury. Żywy daemon, PID, poprawny tekst bez koperty, sam label `Łatka` ani phase label nie są wystarczającym dowodem.
