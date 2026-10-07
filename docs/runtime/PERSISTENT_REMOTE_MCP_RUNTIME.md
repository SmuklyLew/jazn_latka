# Persistent Remote MCP Runtime — architektura hosta ChatGPT

Ten dokument opisuje stan architektury od linii
`16.3.25.5.81-persistent-remote-mcp-runtime`. Jest runbookiem integracyjnym,
nie dowodem, że konkretna powierzchnia ChatGPT ma aktualnie dostęp do zdalnego
runtime.

## 1. Jeden runtime, wiele transportów

Źródłem stanu rozmowy, pamięci, cognition, affect, lineage i finalizacji pozostaje
jeden persistent daemon Jaźni. Transporty są klientami tego samego runtime:

```text
ChatGPT / host capability
        |
        +-- public HTTPS MCP 2026-07-28 Streamable HTTP
        |
        +-- OpenAI Secure MCP Tunnel -> stdio MCP target
        |
        +-- operator_recovery: local executor / run.py (service only)
        v
persistent Jaźń daemon on loopback
        |
        +-- session / memory / cognition / affect
        +-- durable request + turn lineage
        +-- host-visible finalization
```

Żaden transport nie tworzy drugiej Jaźni ani własnego źródła prawdy.

## 2. Publiczny Streamable HTTP

Kod wejścia znajduje się w:

- `latka_jazn/mcp/http_gateway.py` — SDK MCP v2, OAuth/resource-server policy,
  scopes, redacted resources, `/healthz`, `/readyz`, rate limits i operator;
- `latka_jazn/mcp/http_tasks_bridge.py` — wąski adapter dla SEP-2663 Tasks,
  których przypięty MCP Python SDK v2.2.0 jeszcze nie implementuje;
- `latka_jazn/mcp/server.py` — kanoniczna semantyka MCP/Jaźń;
- `latka_jazn/mcp/task_resume.py` — trwały task registry;
- `latka_jazn/mcp/remote_runtime.py` — fail-closed classifier zdalnej trasy.

Produkcyjny listener nie może działać w trybie anonimowym. Builder
`build_public_mcp_gateway()` wymaga `TokenVerifier`, issuer/resource-server
settings i właściwej konfiguracji host/origin. Wbudowane:

```bash
python -X utf8 run.py mcp-http --loopback-dev
```

jest wyłącznie jawnym trybem developerskim na loopback i nie jest ścieżką
publikacji Internetowej.


Zależności SDK/HTTP są capability opcjonalną, a nie częścią minimalnego core.
Dependency Studio ma osobny profil `mcp-http`, dzięki czemu można przygotować
zweryfikowany wheelhouse bez promowania publicznego ingressu do obowiązkowych
zależności zwykłego lokalnego runtime:

```bash
python -X utf8 -m latka_jazn.tools.dependency_studio --json \
  download --profile mcp-http --platform current --python-version <major.minor>
python -X utf8 -m latka_jazn.tools.dependency_studio --json \
  verify --profile mcp-http --platform current --python-version <major.minor>
```

Instalacja pozostaje jawnie offline i wymaga zweryfikowanego bundle. Profil
`mcp-http` nie należy do `activation_profiles` ani domyślnego
`release_profiles`: brak tej capability nie może blokować lokalnej Jaźni,
Ollamy ani Secure MCP Tunnel stdio.

## 3. Narzędzia, resources i scope

Publiczna warstwa eksponuje tylko bounded surface:

- `jazn_generate_visible_reply` — submit jednej nowej tury;
- `jazn_resume_visible_reply` — poll/resume istniejącego requestu;
- `jazn_finalize_reply` — phase-2 z continuation token i SHA-256;
- `jazn_status` — zredagowany status readiness;
- `jazn://runtime/status`, `jazn://memory/status`,
  `jazn://task/{taskId}` — read-only resources.

Audit/operator internals nie są publicznym MCP tool surface. Publiczne wywołania
mają scope per operacja, limity częstotliwości oraz bounds wejścia. Tasks HTTP
przechodzi przez te same admission boundaries co zwykły public tool path.

## 4. MCP 2026-07-28 Tasks

Jaźń reklamuje `io.modelcontextprotocol/tasks` tylko na nowoczesnej ścieżce.
Asynchroniczny submit działa następująco:

1. klient wysyła `tools/call` dla `jazn_generate_visible_reply` z jednym
   stabilnym `request_id`;
2. jeżeli runtime zwraca `poll_runtime`, adapter trwale zapisuje
   task↔`daemon_request_id` w `workspace_runtime/mcp_tasks.sqlite3`;
3. dopiero po trwałym zapisie zwracany jest `resultType="task"`;
4. klient używa `tasks/get` dla tego samego task id;
5. adapter wykonuje `jazn_resume_visible_reply` na tym samym
   `daemon_request_id`, nigdy nie replayuje pierwotnej wiadomości;
6. `tasks/cancel` zapisuje cooperative cancel intent i nie udaje, że runtime
   już się zatrzymał;
7. `tasks/update` istnieje zgodnie z extension contract, ale bieżący
   visible-turn runtime Jaźni nie emituje jeszcze taskowego `input_required`.
   Jeżeli nie istnieje zweryfikowany runtime input transport, adapter kończy
   fail-closed zamiast udawać przyjęcie danych.

Task ID i task state są trwałe między procesami gatewaya. Stare rekordy JSON są
migrowane leniwie do SQLite bez ich usuwania.

## 5. Zdalny ingress hosta

Od 16.3.25.5.113 zwykła wiadomość ChatGPT działa w `remote_only`: zweryfikowana aplikacja/MCP jest jedyną normalną trasą do persistent runtime. Brak bieżącej aplikacji albo kompletnego toolsetu kończy się fail-closed i nie uruchamia local executora, ZIP bootstrapu ani automatycznego handoffu. Local process execution pozostaje wyłącznie jawnym `operator_recovery`.

Publiczny Streamable HTTP ma dwa równoważne, fail-closed tryby evidence.

**Deployment/HTTP probe** wymaga jednocześnie:

- skonfigurowanego endpointu;
- zweryfikowanego uwierzytelnienia;
- zgodności MCP;
- `/healthz` potwierdzającego żywy gateway;
- `/readyz` potwierdzającego gotowy persistent runtime;
- jawnej capability odpowiadającej aplikacji/konektora w bieżącym hoście.

**Connector-observed probe** jest przeznaczony dla ChatGPT, który może wywołać
aplikację Jaźni, ale nie ma lokalnego executora ani ogólnego klienta HTTP. Host
wywołuje read-only `jazn_status`; gateway zwraca samopisujący kontrakt
`jazn_public_mcp_status/v1`. `classify_public_connector_status_failover()`
wymaga dodatkowo dowodu, że bieżący host rzeczywiście wykonał tę akcję, oraz
sprawdza protokół, gateway/runtime instance binding, dokładną wersję i świeżość
statusu/heartbeat. Skopiowany status bez obserwacji wywołania connectora pozostaje
niewystarczający.

Secure MCP Tunnel ma analogiczny niezależny gate: proces, health, readiness oraz
capability hosta muszą być pozytywne.

Untrusted JSON do `host-preflight` nie może ustawić gołego
`remote_runtime_transport_available=true`. Musi przekazać
`remote_runtime_evidence`, które jest ponownie klasyfikowane przez kanoniczny
classifier dla rzeczywistego transportu. Dla public HTTP wolno przekazać albo
parę `health`/`readiness`, albo `connector_status` +
`host_connector_invocation_observed=true`; oba tryby są wzajemnie wykluczające.
Wynik snapshotu zachowuje także typ zweryfikowanego transportu.

## 6. Request identity i utrata transportu

`request_id` jest przydzielany przed pierwszym submit. Po możliwym przekroczeniu
granicy skutku ubocznego nie wolno tworzyć nowego requestu dla tej samej
wiadomości. Wznawianie odbywa się przez ten sam `daemon_request_id` / task.

HTTP timeout, utrata odpowiedzi klienta lub reconnect nie są zgodą na ponowny
`tools/call` z tekstem użytkownika jako nową turą.

## 7. Twarda granica widocznej odpowiedzi

Host może pokazać wypowiedź przypisaną Jaźni wyłącznie po zaakceptowanym
`action=display_exact` z poprawną lineage i finalizacją. Sam `task completed`,
żywy endpoint, heartbeat, gotowy daemon lub sukces HTTP nie są wystarczające.

`generate_then_finalize` oznacza, że host wykonuje bounded language generation
z przekazanego kontraktu i wraca do `jazn_finalize_reply`. Dopiero wynik
finalizatora z `display_exact` jest tekstem do pokazania.

## 8. Pakiet SYSTEM i deployment

Generator paczki rozróżnia:

- kod publicznego Streamable HTTP ingress w SYSTEM;
- lokalny stdio target dla Secure MCP Tunnel;
- zewnętrzne wdrożenie/auth/konektor hosta.

Obecność kodu w ZIP nie ustawia route-ready. Manifest zachowuje
`remote_runtime_route_ready_from_package_alone=false` i wymaga osobnego evidence
transportu oraz host capability.

## 9. Walidacja przed merge

Minimum dla tej linii:

```bash
python -X utf8 -m compileall -q -x 'tests[\\/]archive[\\/]' latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -m "not live_model and not live_mcp" --ignore=tests/archive
python -m pyright --project pyrightconfig.json
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --profile system --json
```

Dodatkowo workflow `persistent-runtime-e2e` uruchamia na Windows i Linux
kontrakty MCP, trwałość Tasks, public HTTP, evidence hosta, lifecycle daemona i
host-visible finalization.

## 10. Granica wdrożenia

Ta aktualizacja może dostarczyć kompletny kod serwera, politykę bezpieczeństwa,
readiness, Tasks, recovery i testy. Nie może natomiast sama utworzyć zewnętrznego
HTTPS endpointu, nadać bieżącemu kontu ChatGPT capability aplikacji/konektora ani
uwierzytelnić zewnętrznego control plane. Te elementy są deployment evidence i
muszą być zweryfikowane osobno w hoście, zanim `remote_runtime` stanie się
aktywną trasą.


## 11. Developer Mode convergence in 16.3.25.5.93

The ChatGPT-facing modern MCP surface now uses one stable client turn identity:

1. ChatGPT calls jazn_turn with a clientTurnId and the exact user message.
2. The transport maps clientTurnId directly to the existing canonical
   request_id before any side effect crosses into the daemon.
3. If the outcome is pending or transport delivery is ambiguous, the returned
   contract points to jazn_resume_turn with the same clientTurnId.
4. jazn_resume_turn never accepts the original message, so recovery cannot
   accidentally become a second conversation turn.
5. If the runtime needs host generation, the existing
   generate_then_finalize -> jazn_finalize_reply -> display_exact boundary is
   unchanged.
6. The persistent task registry and older canonical generate/resume names remain
   compatibility machinery, not a second runtime.

The same adapter is used by public Streamable HTTP and the Secure MCP Tunnel
stdio target. This keeps first-message behavior, retry identity and redaction
consistent across both deployment choices.

The public diagnostics are jazn_status, jazn_health and jazn_memory_status.
Memory status never returns raw autobiographical data or local filesystem paths.
The MEMORY package remains local to the persistent runtime and is not copied
into the ChatGPT sandbox.

This change deliberately does not weaken production authentication. Public
non-loopback Streamable HTTP still requires the configured token verifier and
OAuth resource-server policy. No-auth remains a loopback-only development mode.

There is still one platform boundary outside the repository: ChatGPT must make
the Jaźń app available/selected for the conversation. Tool descriptions can
strongly steer ordinary messages into jazn_turn after selection, but code inside
Jaźń cannot force a global default app for every new ChatGPT conversation.


## 12. Task-state coherence in 16.3.25.5.96.2

The durable Tasks adapter now treats the advertised task TTL as an explicit
server-side backstop. A non-terminal task whose `createdAt + ttlMs` has elapsed
transitions to `failed` with a stable `task_ttl_elapsed` protocol error
instead of remaining pollable forever. `ttlMs=null` remains unlimited.

An `input_required` task is a stable snapshot. Repeated `tasks/get` calls
return the same persisted `inputRequests` and `requestState` without
re-entering `jazn_resume_visible_reply`. This matches SEP-2663 and prevents a
poll loop from repeatedly touching the runtime while the client has not supplied
the requested input.

SQLite task mutations that perform read/modify/write transitions reserve the
write transaction with `BEGIN IMMEDIATE`. The in-process `RLock` remains,
but correctness no longer depends on a single Python gateway object: independent
gateway processes sharing `mcp_tasks.sqlite3` serialize task creation,
state transitions, and cancellation intent at the database boundary.

Unexpected adapter exceptions are still terminal protocol failures, but public
task errors contain only the stable exception class, not raw exception text.
Normal daemon transport ambiguity does not use this exception path:
`jazn_resume_visible_reply` already converts a verified transport outage into
`poll_runtime` for the same `daemon_request_id`, so the user message is never
replayed.

The custom HTTP Tasks bridge remains intentional in this release. The official
MCP Python SDK v2 implements the 2026-07-28 protocol core, while its current
migration/roadmap documentation still lists SEP-2663 Tasks dispatch as not yet
implemented. Removing the bridge before the SDK supplies the extension would
remove working Tasks support rather than simplify it.

External ChatGPT acceptance remains a deployment fact, not a repository fact:
the repository can validate its server, plugin package and task semantics, but
only a real ChatGPT connection to the deployed HTTPS `/mcp` endpoint can prove
host tool discovery and end-to-end `display_exact` delivery.


### SQLite WAL bootstrap contention

WAL mode is durable database state. The task store no longer executes
`PRAGMA journal_mode=WAL` for every short-lived connection. Store
initialization first observes the current journal mode and only performs the
mode transition when necessary. BUSY/LOCKED during that transition is retried
with a fixed maximum of six attempts and bounded exponential delay; exhaustion
fails closed. Task state changes still use `BEGIN IMMEDIATE` so the
read/modify/write invariant remains serialized across independent processes.


## 13. Operational convergence in 16.3.25.5.107

The public deployment path now treats remote ingress as an operated persistent
service, not merely as code that can be started:

- production startup validates the canonical nested `run.py status --json`
  evidence, including runtime/gateway binding and exact runtime version;
- a verified existing runtime supervisor is reused, otherwise the deployment
  starts the canonical supervisor and waits boundedly for identity + heartbeat
  evidence before exposing the gateway;
- `/healthz` remains process liveness while `/readyz` is runtime readiness;
- `deploy/chatgpt_mcp/deployment.contract.json` versions the deployment-facing
  wire/readiness/security contract;
- Cloudflare Tunnel and systemd examples keep the daemon private, keep secrets
  outside source control and require a reviewed cloudflared tag/digest;
- MEMORY package production verifies its v3 exact-set manifest against the
  staged tree before archive/transport creation, so an unlisted/missing member
  fails at the producer boundary as well as during runtime attach.

The only normal continuity route for ordinary ChatGPT turns is a **currently
callable and verified** remote Jaźń app. Local process execution is no longer a
fallback for ordinary chat; it is available only in explicit
`operator_recovery`. Losing or gaining a ChatGPT-local executor therefore does
not participate in ordinary ingress routing. Conversely, a healthy public
endpoint without a callable Jaźń app in the current message is not enough to set
`remote_runtime_available=true`.

Operational procedures, failure injection and rollback are specified in
`docs/runtime/PERSISTENT_REMOTE_MCP_OPERATIONS.md`.

## 14. Remote-only ChatGPT ingress in 16.3.25.5.113

Normalna wiadomość ChatGPT wymaga bieżącej ekspozycji dokładnie czterech
kanonicznych akcji: `jazn_status`, `jazn_generate_visible_reply`,
`jazn_resume_visible_reply`, `jazn_finalize_reply`. Gate jest sprawdzany dla
bieżącej wiadomości; sam stan installed, URL, manifest, poprzednia tura ani
wcześniejszy @mention nie wystarczają.

`jazn_status` publikuje wersjonowany fingerprint wymaganej powierzchni
(`required_chatgpt_turn_tools_revision` i SHA-256). Gdy ChatGPT widzi stary
lub niekompletny snapshot narzędzi, operator ma odświeżyć/reutworzyć/publikować
aplikację po stronie ChatGPT. Nie wolno zastępować brakującej akcji local
executorem.

Oficjalna dokumentacja OpenAI rozdziela:
- publiczny remote MCP dla publicznie osiągalnego HTTPS endpointu;
- Secure MCP Tunnel dla prywatnego/lokalnego MCP, z outbound-only połączeniem;
- ekspozycję aplikacji w ChatGPT, która jest capability bieżącej wiadomości;
- Refresh narzędzi po zmianach serwera, ponieważ aktualizacje action/tool
  surface nie są automatycznie włączane.

Źródła operacyjne:
- https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/api/docs/guides/custom-mcp-server


## 15. ChatGPT Desktop initialize-era tool visibility convergence — v119.2.0

The canonical stdio MCP target now guarantees the same model-visible metadata
for the required four ChatGPT turn tools whether the client uses modern
2026-07-28 discovery or initialize-era 2025-11-25 discovery.

Only the canonical turn tools are promoted to
`ui.visibility=["model","app"]`; app diagnostics and legacy aliases keep their
previous app-only visibility. This avoids exposing operator/audit surfaces merely
because a Desktop client negotiated an older MCP revision.

Acceptance requires both protocol and host evidence: the initialize-era
`tools/list` must return the complete canonical toolset with model-visible
metadata, modern discovery must preserve the same canonical visibility, the
current ChatGPT message must actually expose the four tools, and fresh
`jazn_status` must prove the expected runtime/version/readiness.
