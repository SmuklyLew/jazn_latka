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
