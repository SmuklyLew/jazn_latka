# Jaźń v16.3.25.5.76.1 — ChatGPT remote-runtime route convergence

## Cel i granica odpowiedzialności

Ta aktualizacja naprawia repozytoryjne przyczyny, przez które host ChatGPT mógł mimo dostępnej, jawnie zweryfikowanej trasy zdalnej ponownie uzależniać zwykłą turę od lokalnego executora, a także dwa błędy na styku NLP/finalization i jeden błąd zgodności MCP.

Nie deklaruje, że kod Jaźni naprawia `TransportTimeoutError`, który zachodzi **przed utworzeniem procesu** w infrastrukturze hosta ChatGPT. Kod lokalnej paczki zaczyna działać dopiero po uzyskaniu wykonania albo przez istniejącą zdalną capability. Celem 76.1 jest więc: preferować już zweryfikowaną persistent route, zachować idempotentny poll/resume i nie tworzyć fałszywych decyzji z tekstu cytowanego przez użytkownika.

## Zakres audytu architektury

Strukturalny audyt aktywnego drzewa (bez `tests/archive` i cache) sparsował przez AST **1001 plików Python, 207 278 linii, 8121 funkcji i 1123 klasy**, bez błędów parsowania. Największe warstwy to:

- `latka_jazn/core`: 240 plików / 53 944 linii / 1786 funkcji / 367 klas;
- `latka_jazn/memory`: 83 / 24 121 / 938 / 217;
- `latka_jazn/tools`: 134 / 38 261 / 1405 / 149;
- `latka_jazn/nlp`: 48 / 5178 / 198 / 75;
- `latka_jazn/mcp`: 11 / 2582 / 82 / 10;
- `latka_jazn/model_adapters`: 13 / 1910 / 75 / 16;
- `latka_jazn/nlp_reasoning`: 20 / 1559 / 66 / 21;
- `latka_jazn/bootstrap`: 13 / 2372 / 54 / 8;
- `latka_jazn/adapters`: 3 / 357 / 26 / 3.

Audyt strukturalny wszystkich funkcji został uzupełniony semantycznym przeglądem ścieżek, które rzeczywiście uczestniczą w badanym błędzie: host capability aggregation, bootstrap/recovery, daemon/supervisor, Secure MCP tunnel bootstrap i readiness, MCP stdio server, ChatGPT pre-response/finalization gate, adapter ChatGPT, model-adapter boundaries, control-text NLP, compound question/component coverage i memory source routing. Nie znaleziono ścieżki, w której `engine.py`, model adapter albo parser NLP mógłby naprawić hostowy timeout występujący przed spawnem procesu.

## Źródło problemu 1 — routing local-first mimo verified remote

`secure_tunnel.classify_remote_runtime_failover()` już przed tą zmianą fail-closed wymagał równocześnie:

- `process_running=true`,
- `healthy=true`,
- `ready=true`,
- jawnej `host_connector_capability_available=true`.

Dopiero taki wynik może ustawić `remote_runtime_transport_available=true`. Mimo tego `aggregate_host_executor_observations()` wybierał lokalny executor zawsze, gdy jakakolwiek lokalna powierzchnia była dostępna. Było to sprzeczne z `AGENTS.chatgpt.md`: zweryfikowana persistent route miała być używana przed lokalnym bootstrapem.

### Naprawa

Dodano `resolve_verified_remote_route()`. Gdy istnieje już pozytywny remote-runtime gate, agregator wybiera `REMOTE_RUNTIME` także wtedy, gdy lokalny executor jest dostępny. Local executor pozostaje bootstrapem/recovery/fallbackiem, jeśli remote capability nie została jawnie zweryfikowana.

To odpowiada oficjalnemu modelowi OpenAI Secure MCP Tunnel. `tunnel-client` jest agentem utrzymującym prywatny/localhost MCP dostępny dla produktów OpenAI bez wystawiania serwera do publicznego Internetu. Długowieczny runtime powinien być zarządzany i osobno raportować liveness/readiness; samo istnienie lokalnego MCP nie tworzy connectora w ChatGPT. Po uruchomieniu zdrowego runtime'u tunnel musi być rzeczywiście podłączony w ChatGPT jako Connector/App.

## Źródło problemu 2 — zbyt gruby loader aplikacji ChatGPT

Dotychczasowy `CHATGPT_PROJECT_INSTRUCTIONS.txt` bezwarunkowo zaczynał od local-executor probe, a następnie duplikował część lifecycle, request-id, polling i finalization należących już do `AGENTS.chatgpt.md`. To tworzyło dwa równoległe kontrakty i powodowało, że host mógł wejść w długo wiszącą powierzchnię wykonawczą zanim w ogóle rozważył gotową persistent route.

### Naprawa

Loader jest teraz cienki i remote-first:

1. najpierw sprawdza już zweryfikowaną `remote_runtime` (managed-runtime evidence + jawna connector/app capability);
2. dopiero przy jej braku wykonuje jedną minimalną próbę lokalnego process execution i maksymalnie jedną rzeczywiście niezależną alternatywę;
3. błąd hosta przed spawnem nie jest dowodem braku `/mnt/data`, ZIP-a, filesystemu ani runtime;
4. fizyczny SYSTEM jest weryfikowany i materializowany kontraktem `CHATGPT_BOOTSTRAP.py`;
5. gdy żywy daemon/zaufany marker wskazuje kanoniczny `active_root`, host nie może arbitralnie przełączyć się na równoległą rozpakowaną kopię tej samej wersji;
6. po zweryfikowaniu runtime pełny lifecycle/routing/recovery/finalization przejmuje `AGENTS.md` + właściwy runbook hosta.

Instrukcja nie udaje capability produktu: nie może sama stworzyć executora, Secure MCP tunnel association ani Connectora/App, których bieżący host nie udostępnia.

## Źródło problemu 3 — cytowany kod wpływał na aktywną intencję

`DialogueIntentClassifier` miał już poprawny `extract_intent_control_text()`, który maskuje fenced code, inline code i cytowany materiał przed klasyfikacją intencji. Jednak późniejsze warstwy ponownie analizowały surowy tekst użytkownika:

- `RuntimeAnswerValidator`,
- `component_coverage_ledger`,
- `MemoryUseGate`,
- `build_typed_source_policy()`,

W praktyce pytania znajdujące się wyłącznie we wklejonym loaderze mogły stać się rzekomymi komponentami compound question albo fałszywie aktywować recall/politykę źródeł pamięci.

### Naprawa

Wszystkie wymienione konsumenty aktywnej intencji używają teraz tego samego `control_text`. Cytowany materiał nadal jest evidence dostępne dla odpowiedzi, ale nie jest traktowany jako nowe polecenie, pytanie lub prośba o pamięć.

To naprawia realnie odtworzony przypadek `missing_compound_question_components`, w którym pytania wewnątrz cytowanej instrukcji zostały potraktowane jak pytania bieżącej tury.

## Źródło problemu 4 — MCP version/capability negotiation

Bazowy `JaznMcpServer` zwracał w `initialize` wersję przesłaną przez klienta, nawet gdy serwer jej nie implementował. Jednocześnie reklamował legacy extension `io.modelcontextprotocol/tasks` niezależnie od negocjowanej wersji.

Specyfikacja MCP 2025-11-25 wymaga, aby inicjalizacja była pierwszą fazą, żeby strony uzgodniły protocol version i capabilities. Jeżeli serwer nie wspiera wersji klienta, ma odpowiedzieć inną wspieraną wersją, preferencyjnie najnowszą. Operacje opcjonalne wolno wykorzystywać tylko po ich negocjacji.

Tasks w 2025-11-25 są eksperymentalnym standardem durable state-machine z własnymi capabilities (`tasks.list`, `tasks.cancel`, `tasks.requests.*`) i standardowym lifecycle/result contract. Legacy adapter Jaźni ma inny, wcześniejszy kontrakt (`tasks/get`, `tasks/cancel`, `tasks/update`) i nie implementuje pełnego standardowego Tasks.

### Naprawa

- jawnie obsługiwane wersje: `2025-11-25` oraz legacy `2025-06-18`;
- nieznana wersja nie jest echo-wana — serwer odpowiada najnowszą wspieraną;
- dla `2025-11-25` reklamowane są `tools`, ale nie standard MCP Tasks;
- legacy task extension jest reklamowane tylko dla negocjowanego `2025-06-18`;
- legacy `tasks/get|cancel|update` zwracają `-32601 Method not found` w nowoczesnej sesji, aby nie podszywać się pod standard 2025-11-25;
- trwałość operacji Jaźni pozostaje realizowana przez jawne narzędzia `jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_finalize_reply` oraz stabilne request identity.

## Źródło problemu 5 — pending poll przed turn_id/trace_id

`poll_runtime` nie renderuje tekstu runtime. Mimo tego wcześniejszy pre-response gate wymagał dla niego tak samo silnego bindu jak dla `display_exact`: `turn_id`, `trace_id` i message digest. Długie accepted work może jeszcze nie mieć tych identyfikatorów w momencie pierwszego poll, mimo że posiada trwały `daemon_request_id`.

### Naprawa

`poll_runtime` może zachować wiązanie przez `daemon_request_id` + poll command po potwierdzeniu invocation. `generate_then_finalize` i `display_exact` nadal wymagają silnego current-turn binding; wyjątek dla poll nie daje prawa do wyświetlenia runtime-owned text.

## NLP/AI — decyzja architektoniczna

Nie przepisano całego NLP, ponieważ audyt nie wykazał związku między parserem języka a pre-spawn `TransportTimeoutError`. Obecny provider-based model jest zgodny z modularnym pipeline Stanza: tokenizacja/sentence segmentation, MWT, POS, lemma i dependency parse mają jawne zależności, a NER jest osobnym procesorem. Brak lokalnego modelu powinien degradować konkretną capability, a nie blokować całą rozmowę.

Osobno zachowano granicę epistemiczną dla confidence. Heurystyczny score w systemie nie jest automatycznie prawdopodobieństwem poprawności. Badanie Guo et al. pokazuje, że nawet nowoczesne sieci neuronowe mogą być źle skalibrowane, a kalibrację należy mierzyć na danych. Dlatego ta aktualizacja nie „ulepsza” confidence przez arbitralne stałe; przyszła kalibracja intencji wymaga oznakowanego korpusu, metryk per-intent/OOD i osobnej procedury calibration/evaluation.

## Testy i zgodność

Dodano regresje dla:

- verified remote runtime preempts usable local bootstrap;
- cytowany loader nie tworzy compound user question;
- cytowane pytania o pamięć nie aktywują memory routing;
- nieobsługiwana MCP version nie jest echo-wana;
- MCP 2025-11-25 nie reklamuje niezaimplementowanego Tasks;
- legacy task methods nie są dostępne pod 2025-11-25;
- thin loader sprawdza remote route przed local probe;
- loader respektuje kanoniczny `active_root`.

Przed zmianą istniejących aktywnych testów zapisano ich byte-exact snapshoty v16.3.25.5.76.0 w `tests/archive/v16.3.25.5.76.0-chatgpt-remote-runtime-route-convergence/` z wersją źródłową w nazwie każdego pliku.

Lokalna walidacja końcowej postaci patcha:

- nowe regresje v76.1: `8 passed`;
- szeroki selektor ChatGPT/MCP/host/conversation po aktualizacji oczekiwań kontraktowych: `348 passed`, `1333 deselected`;
- trzy znane testy granicy pamięci zostały z tego selektora jawnie wyłączone po wcześniejszym potwierdzeniu, że identycznie padają na nietkniętym v76; dotyczą istniejącej granicy `workspace_runtime/memory` vs `workspace_runtime/core_state/memory_runtime` i nie zostały zamaskowane przez zmianę testów;
- 12 zmienionych aktywnych testów ma byte-exact snapshot v16.3.25.5.76.0; kontrola snapshotów: `12/12 byte_exact=True`;
- `compileall` aktywnego kodu: OK;
- Test Studio contract catalog: zsynchronizowany kanonicznym generatorem.

Pełny lokalny pytest przekroczył limit czasu hosta po rozpoczęciu kolekcji/wykonania. Ostateczną pełną macierz, Pyright 1.1.411, metadata sync, package smoke i cross-platform gate wykonuje obowiązkowy `release-hardening` po pushu. Lokalna kopia SYSTEM nie zawiera `.git`, więc `release_metadata_sync` słusznie odmawia tworzenia provenance bez `git rev-parse HEAD`; metadanych nie edytowano ręcznie.

## Znany wcześniejszy problem poza zakresem 76.1

Bazowy v76 ma co najmniej trzy aktywne testy oczekujące, że wybrane runtime-write/ledger files trafią do `workspace_runtime/memory`, podczas gdy implementacja kieruje je do operacyjnego `workspace_runtime/core_state/memory_runtime`. Weryfikacja porównawcza pokazała identyczne failure na bazie v76. Rozstrzygnięcie wymaga osobnej decyzji kontraktowej: które z tych rekordów są autobiograficzną MEMORY, a które operacyjnym core state. Ta aktualizacja nie przenosi danych między tymi granicami bez takiej decyzji.

## Źródła zewnętrzne

- OpenAI Secure MCP Tunnel / `tunnel-client`: https://github.com/openai/tunnel-client
- OpenAI tunnel-client — podłączenie ChatGPT Connector po gotowości runtime: https://github.com/openai/tunnel-client/blob/master/docs/end-user-guide.md
- OpenAI Help — Apps SDK: https://help.openai.com/en/articles/12515353-build-with-the-apps-sdk
- OpenAI Help — Developer mode and MCP apps in ChatGPT: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- MCP 2025-11-25 — lifecycle, version i capability negotiation: https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- MCP 2025-11-25 — Tasks: https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks
- Stanford Stanza — Pipeline and Processors: https://stanfordnlp.github.io/stanza/pipeline.html
- Guo, Pleiss, Sun, Weinberger, *On Calibration of Modern Neural Networks*, ICML/PMLR 2017: https://proceedings.mlr.press/v70/guo17a.html
