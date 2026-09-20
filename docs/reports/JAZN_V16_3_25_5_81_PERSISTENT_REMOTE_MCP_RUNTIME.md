# Jaźń v16.3.25.5.81 — Persistent Remote MCP Runtime

## Cel

Wersja 16.3.25.5.81 przebudowuje integrację hosta tak, aby zwykła rozmowa ChatGPT
nie zależała od powodzenia lokalnego executora bieżącej tury. Persistent runtime
Jaźni pozostaje jednym systemem, a lokalny executor, publiczny Streamable HTTP i
Secure MCP Tunnel są wyłącznie transportami/trasami do tego samego runtime.

## Zaimplementowany zakres

Kod obejmuje warstwy serwera, transportu, trwałości, routingu hosta, operatora,
pakowania i CI, a nie pojedynczy adapter:

- `latka_jazn/mcp/server.py` — MCP 2026-07-28, discovery, Tasks i resources;
- `latka_jazn/mcp/task_resume.py` — SQLite durable Tasks i no-replay resume;
- `latka_jazn/mcp/http_gateway.py` — Streamable HTTP, auth, scopes, limits,
  health/readiness, resources i bounded public tool surface;
- `latka_jazn/mcp/http_tasks_bridge.py` — brakująca w przypiętym SDK v2.2.0
  powierzchnia SEP-2663 Tasks, bez przejmowania pozostałego routingu SDK;
- `latka_jazn/mcp/remote_runtime.py` i `latka_jazn/mcp/secure_tunnel.py` —
  niezależne fail-closed classifiers transportów;
- `latka_jazn/bootstrap/chatgpt_host_preflight_parse.py` oraz host capability
  aggregation — dodatnia zdalna trasa musi być wyprowadzona z pełnego evidence,
  nie z gołego boola;
- `latka_jazn/runtime/turn_runtime.py` i `capability_matrix.py` — jawny model
  transportów i capabilities;
- `latka_jazn/cli.py` — kanoniczny operator `mcp-http` dla jawnego loopback
  development; production builder wymaga verifiera;
- generator SYSTEM — deklaruje bundling kodu bez udawania gotowego deploymentu;
- `AGENTS.chatgpt.md` — host preferuje już zweryfikowany remote runtime, lecz
  zachowuje accepted-visible-turn boundary;
- `persistent-runtime-e2e` — Windows/Linux obejmuje nową architekturę;
- mutujące joby `release-hardening/manifest_sync` i
  `Stable test contracts/sync_catalog` współdzielą jeden branch-level
  concurrency gate, więc nie ścigają się już przy automatycznych commitach
  metadanych i katalogu testów.

## Tasks i trwałość

Task handle jest zwracany dopiero po trwałym utworzeniu rekordu w
`workspace_runtime/mcp_tasks.sqlite3`. Rekord mapuje task na istniejący
`daemon_request_id`, zachowuje lineage i umożliwia poll po restarcie gatewaya.
Historyczne rekordy JSON są migrowane leniwie.

`tasks/cancel` jest cooperative intent. `tasks/update` nie udaje konsumpcji
host-input: bieżący visible-turn runtime nie emituje jeszcze taskowego
`input_required`, więc brak zweryfikowanego runtime input transportu kończy się
fail-closed.

## Publiczny ingress i bezpieczeństwo

Publiczna powierzchnia nie udostępnia operator/audit internals. Produkcja wymaga
SDK `TokenVerifier` oraz issuer/resource-server policy. Anonimowy tryb istnieje
wyłącznie jako jawny loopback development. Tasks path ma te same scope, bounds,
standardowe nagłówki MCP, body limit i rate admission co podstawowy public path.

`/healthz` potwierdza tylko żywy gateway. `/readyz` wymaga gotowego runtime.
Żaden z nich sam nie oznacza host-usable ChatGPT route.

## Host failover

`host-preflight` nie ufa już
`remote_runtime_transport_available=true` przekazanemu bez dowodów. Dla
publicznego HTTP wymaga endpoint/auth/protocol/health/readiness/host capability;
dla tunelu wymaga process/health/readiness/host capability. Snapshot zachowuje
typ zweryfikowanego transportu.

Jeżeli remote route jest zweryfikowana, host może ominąć lokalny executor dla
zwykłej tury. Jeżeli nie jest zweryfikowana, lokalna awaria pre-spawn nie może
zostać przedstawiona jako awaria ZIP-a, filesystemu ani persistent runtime.

## Finalizacja

Remote MCP nie zmienia zasady autorstwa: `poll_runtime` wznawia ten sam
request, `generate_then_finalize` wraca do tego samego kontraktu, a tekst wolno
pokazać jako wypowiedź Jaźni tylko po zaakceptowanym `display_exact`.

## Walidacja i CI

Ta linia ma dedykowane testy nowoczesnego MCP, trwałych Tasks, publicznego HTTP,
resources, CLI, package contract i host remote-evidence oraz uruchamia
`persistent-runtime-e2e` na Windows i Linux. Pełny merge-gate pozostaje
własnością release-hardening/pyright/stable-test-contract workflows.

Raport należy uznać za release-ready dopiero dla konkretnego HEAD, dla którego
wymagane workflow zakończyły się sukcesem. Sam fakt, że wcześniejszy commit był
zielony, nie jest dowodem dla późniejszego HEAD.

## Źródła protokołu

- MCP SEP-2663 Tasks extension:
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2663-tasks-extension.md
- MCP SEP-2243 HTTP standardization:
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2243-http-standardization.md
- MCP Python SDK v2.2.0 release notes:
  https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0
- OpenAI Developer mode / MCP apps:
  https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt

## Truth boundary

Kompletny kod i zielone testy nie mogą nadać bieżącej powierzchni ChatGPT
zewnętrznej capability. Publiczny HTTPS deployment, auth/control-plane i
host-side app/connector pozostają osobnym evidence. Żaden endpoint, task handle,
tunnel process ani heartbeat nie jest też samodzielnym dowodem accepted visible
turn.
