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

Publiczny Streamable HTTP jest host-usable dopiero, gdy jednocześnie:

- endpoint jest skonfigurowany;
- uwierzytelnienie jest zweryfikowane;
- protokół MCP jest zgodny;
- `/healthz` potwierdza żywy gateway;
- `/readyz` potwierdza gotowy persistent runtime;
- bieżący host ChatGPT jawnie udostępnia odpowiadającą aplikację/konektor.

Secure MCP Tunnel ma analogiczny niezależny gate: proces, health, readiness oraz
capability hosta muszą być pozytywne.

Untrusted JSON do `host-preflight` nie może ustawić gołego
`remote_runtime_transport_available=true`. Musi przekazać
`remote_runtime_evidence`, które jest ponownie klasyfikowane przez kanoniczny
classifier dla rzeczywistego transportu. Wynik snapshotu zachowuje także typ
zweryfikowanego transportu.

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
