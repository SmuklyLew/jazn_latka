# Etap 05 — audyt ingress i odporności (iteracja 2026-11-25)

Baza: e291870dd6c831307408894b5c669590a2d71f0e. Zakres audytu statycznego jest częściowy; nie stanowi odbioru live ani dowodu braku wszystkich obejść.

| Powierzchnia | Obserwacja kodu | Stan |
|---|---|---|
| main.py / CLI chat-gpt | ensure obowiązkowe; błąd transportu zachowuje request_id, host_diagnostic | poprzednie CI PASS, live NOT_RUN |
| main.py / chat-ollama | ensure przed discovery, błąd modelu nie wysyła tury | poprzednie CI PASS, live Ollama NOT_RUN |
| main.py / chat, direct_message, jawne OpenAI | wybór modelu przed ensure nadal wymaga konwergencji | OPEN |
| core/chat_command_contract.py / JSONL | daemon_bound korzysta z DaemonConversationSession; default false pozwala tworzyć RuntimeSessionWorker/JaznRuntimeSession; phase-2 deleguje do ConversationRunner.finalize_candidate | audyt wszystkich wywołań oraz authority phase-2 OPEN; nie usuwać debug/test bez rozpoznania |
| tools/jazn_run_studio/chat.py + validation_worker.py | trwały request przed wysłaniem, jeden pipe write, poll po tym samym ID, worker weryfikuje request/session/turn/trace i lokalny visible gate | weryfikacja niezależnej lineage/persistence/instancji oraz negatywna macierz OPEN |
| core/chat_command_contract.py / runtime_owned_visible_reply_verified | sprawdza truth, hash, answer/execution state i author_source; samo to nie dowodzi persistence ani instancji | OPEN |
| mcp/http_gateway.py, mcp/server.py | powierzchnie generate/resume/finalize; pełny audyt principal/request/instance oraz utraty transportu OPEN | real ChatGPT/MCP BLOCKED |
| model_adapters/factory.py | jawny adapter omija resolver; dodatkowy wspólny opt-in paid OpenAI w tej zmianie | CI pending; direct constructor oraz autoryzacja innych endpointów/cloud nadal OPEN |
| core/model_executor_preflight.py | loopback to lokalizacja endpointu, nie dowód lokalności inferencji; external_model dostępny konfiguracyjnie | Ollama cloud/redirect, SIWC i allow_network OPEN |
| runtime/resilience.py + bridge/secure_host_runtime_gateway.py | TransportSupervisor istnieje i jest używany przez gateway; nie wykazano integracji ze wszystkimi adapterami | circuit breakers dla inferencji, trwałość i fault injection OPEN |
| tools/release_readiness.py | wcześniej rozmowa bez daemona oraz retry nowej wiadomości; obecnie osobny negatywny test, pojedynczy submit na tym samym izolowanym porcie po live status, obowiązkowy display_exact | CI pending |
| release-hardening.yml | poprzedni raport 14/15 exit_code=1 maskowany przez tee; shell: bash włącza pipefail, oba acceptance uruchamiane również na push tej gałęzi | CI pending |

Źródła: kod wskazanych modułów na bazowym SHA, release-hardening 45553986336/job/139005398994 (14/15, chat_gpt_turn_and_integrity_consensus FAIL), Ubuntu 139002758226 (4561 PASS, 25 SKIP, 6 subtests PASS), E2E 45553986324 (Windows/Ubuntu PASS); dokumentacja GitHub Actions workflow syntax / shell: bash.

Kryterium końcowe: zero nieautoryzowanych nowych wypowiedzi we wszystkich testowanych integracjach, brak replayu, zachowanie sesji, daemon żywy po awarii modelu, jawna zgoda na transfer, komplet wymaganych bramek Windows/Ubuntu oraz rzeczywista Ollama. Nie utożsamiać PASS symulacji z odbiorem rzeczywistego LLM/MCP. Brak MCP toolsetu i lokalnego worktree/exec potwierdzonego na hoście; live testy NOT_RUN. Nie wykonano płatnego API ani zmian prywatnej MEMORY.

### Aktualizacja: klient i model transport
- Potwierdzono, że `apply_model_channel_config` kopiował `allow_paid_openai_api` z żądania do config tury. Nowa kontrola ogranicza permission do przecięcia operator/klient. Adres docelowy, chmurowe modele Ollama, przekierowania, fallback adaptera i inne ścieżki inferencji nadal wymagają audytu.
- Circuit breaker został połączony z konkretną granicą POST /api/chat, współdzielony między adapterami w tym samym procesie, z izolacją per model i root. CI pending. Test loopback nie jest testem rzeczywistego modelu ani live daemona.
- JSONL `daemon_bound=False` nadal tworzy RuntimeSessionWorker, a host_visible_reply deleguje do ConversationRunner.finalize_candidate. Audyt i migracja wymagają zachowania testów phase-2, powiązania z właściwą instancją i persistence; OPEN. Nie deklarować pełnej Runtime Identity Authority.

### Granica adresu OpenAI API i timeoutu
- `model_api_base` jest teraz adresem operatora, nie uprawnieniem klienta; próba nadpisania w konfiguracji tury kończy się ValueError przed użyciem tak zmienionego adaptera. Brak dowodu pełnej autoryzacji redirectów, innych endpointów, env oraz fallback adaptera.
- Model timeout wymaga skończonej dodatniej liczby; limit górny i pełny budżet wykonania pozostają OPEN. Regresje syntetyczne, CI wymagane.

### JSONL / phase-2 — kolejna iteracja
- Publiczny bridge nie tworzy już in-process session i nie dopuszcza one-shot degraded. Każda próba ma prealokowany request_id; po utracie wyniku nie replayować. ChatGPT JSONL nie rekonstruuje phase-1 po stronie klienta.
- JSONL host_visible_reply przed istniejącym finalizatorem sprawdza trwałe powiązanie i aktualny autoryzowany job/instance/version/root/heartbeat. Snapshot joba zwraca instance ID. To dodatkowa kontrola ingress, nie nowa finalizacja, nie atomowy lease; CLI host-finalize i MCP wymagają osobnego audytu. Pozostałe kanały, ACK i live Ollama OPEN; CI pending.

### Wspólna autoryzacja publicznej phase-2
- Jedna funkcja `authorize_public_host_finalization` (JSONL, oba dispatchery host-finalize, MCP server/public HTTP backend, legacy record-final-reply, helper zapisujący). Kontrakt wymaga live daemon job, a nie samego tokenu lub hasha. MCP endpoint jest konfiguracją operatora; niedozwolony endpoint odrzucony. CLI nie promuje niepotwierdzonego ACK do accepted display.
- Transakcyjne funkcje wewnętrzne pozostają dostępne dla unit-testów; żadna z wymienionych publicznych tras nie powinna ich wywołać bez bramki. Audyt dalszych callerów, atomowy lease, ACK/recovery, restart, real MCP/Ollama nadal OPEN. CI nowego SHA wymagane.

### Runtime-first i przygotowanie PC
- Auto chat, jawne OpenAI, direct_message oraz daemon-submit/send przenoszą sprawdzenie daemona przed wybór/probe modelu; auto chat używa tego samego ensure receipt. Usunięto pozostały TTY Ollama fallback in-process. Nowe CI wymagane. Debug-direct, pełna authoritatywność phase-2 i pozostałe adaptery nadal do audytu. Real PC acceptance: STAGE05_PC_ACCEPTANCE.md (NOT_RUN).

### Pozostałe adaptery transportowe
- OpenAI-compatible, OpenAI Responses i SIWC mają wspólny process-local circuit per root/provider/endpoint/model; syntetyczne testy bez sieci. Compatible nie ponawia POST przy niejednoznacznym wyniku ani odmowie auth, z zachowaniem negocjacji 404/405. SIWC partial stream nie jest sukcesem. Windows Responses wyłącza redirect. CI pending. Pełna autoryzacja endpointów, cloud, pozostałych redirectów, atomowość phase-2 i realny odbiór nadal OPEN.

### Publiczny ACK daemona
- /chat-finalization accepted wymaga teraz odczytu kanonicznego consumed capture z walidacją envelope/projection i zgodności całej lineage pod lockiem zadania. Brak zapisu nie może przez ten endpoint zakończyć joba. To atomowa kontrola ACK względem przejścia joba, nie atomowa autoryzacja całej transakcji hosta. CI pending, pozostałe ryzyka niezamknięte.

### Etap 05 — granica HTTP inferencji (baza b8479d714b2b02c97d26a4a54a1ad0949fbc3b19)
- Native Ollama (probe i POST) oraz OpenAI-compatible: loopback-only, bez automatycznych przekierowań i proxy środowiskowego. Bezpośredni transport nie może ominąć preflight dla nieautoryzowanego URL. OpenAI Responses urllib odrzuca redirect; Windows już stosuje MaximumRedirection 0, SIWC ma własną ochronę. Bez zmiany globalnego opener/lifecycle.
- 30 nowych przypadków syntetycznych: 20 redirect GET/POST, 8 niedozwolonych URL, bezpośrednia próba obu adapterów i proxy. Testy lokalnego HTTP, nie realnego LLM. CI pending; local pytest NOT_RUN. Nie dowodzi braku dalszej inferencji cloud w serwerze loopback. Pełna autoryzacja, budżet, atomowy phase-2 i Studio nadal OPEN. Źródła: https://docs.python.org/3/library/urllib.request.html oraz https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html. Bez zmian master, MEMORY, płatnego API, poprzednich testów. Zachowano wersję nieopublikowanego kandydata v127.30.10, local worktree/usage unknown.

### Etap 05 — rozróżnienie modeli Ollama cloud i lokalnych
- Resolver discovery /api/ps i /api/tags korzysta z tej samej ochrony loopback, proxy i redirect. Jawne selektory -cloud/:cloud oraz wpisy remote_model/remote_host nie mogą zostać automatycznie wybrane jako lokalne; wspólna lista wykluczeń obejmuje aliasy z /api/ps i /api/tags. Native i compatible Ollama odrzucają jawne selektory cloud przed wysłaniem promptu. To negatywna kontrola, nie pełne poświadczenie lokalności dowolnego aliasu, dowolnego proxy lub konfiguracji serwera. Operator musi zweryfikować OLLAMA_NO_CLOUD/disable_ollama_cloud w działającej usłudze. Źródła: https://docs.ollama.com/faq, https://docs.ollama.com/cloud, https://github.com/ollama/ollama/blob/main/docs/openapi.yaml.
- 6 nowych syntetycznych przypadków. CI pending, local pytest NOT_RUN; atomowy phase-2, Studio, pełna autoryzacja zewnętrznej inferencji i real PC OPEN. Zachowano wersję nieopublikowanego kandydata v127.30.10. Brak zmian master, MEMORY, płatnego API oraz wcześniejszych testów.

### Etap 05 — Studio: niezależny odczyt dowodu zaakceptowanej tury
- Baza 942c20580e81b6751bd4cdb12e9df49ba4966794: 9/9 workflow PASS (poprzedni egress także 9/9), Release Hardening 14/14, Ubuntu 4675 PASS/25 SKIP/6 subtests (139336956132), readiness 16/16 exit_code=0 (139339814022). Regresja i finalizacja na zsynchronizowanym HEAD.
- Publiczny worker Studio sprawdza endpoint operatora, live root/instance/heartbeat/integrity/provenance, uwierzytelniony GET dokładnie tego joba oraz zgodność request/session/turn/trace/text. Odtwarza i porównuje kanoniczny MessageEnvelope z kontraktu, sprawdza dokładny hash-bound rekord rozmowy niezależnym odczytem. Nie generuje, nie persistuje, nie replayuje. Stary validate pozostaje wewnętrznym testem struktury, publiczny main nie używa go jako samodzielnego dowodu. Studio wymaga live_authority_verified przed chat_final/GUI ACK. Bez dowodu zachowuje request_id.
- 13 nowych syntetycznych scenariuszy z prawdziwym zapisem syntetycznego rekordu; nie wykonano lokalnego pytest. CI wymagane. Ograniczenia: dowód dotyczy prezentacji lokalnego zaakceptowanego wyniku, nie osobnej ścieżki archiwizacji terminalnej porażki ani dowodu instancji przed submit. Restart/utrata joba może blokować prezentację do recovery, nie autoryzuje replayu. Atomowy phase-2, ACK/recovery oraz pełna autoryzacja inferencji nadal OPEN. Numer nieopublikowanego kandydata pozostaje v127.30.10; bez master/produkcji/MEMORY/płatnego API. Worktree/usage unknown.
