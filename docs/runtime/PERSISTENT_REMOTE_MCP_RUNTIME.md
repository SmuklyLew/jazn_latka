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
        +-- local executor / run.py (bootstrap i recovery)
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

## 5. Zdalny failover hosta

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


## 12. Task-state coherence in 16.3.25.5.96

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
