# Jaźń v16.3.25.5.95.1 — ChatGPT real MCP ingress convergence

## Cel

Wersja 5.95.1 domyka merge-hardening linii 5.95 i przenosi kryterium sukcesu z "repozytorium zawiera kod MCP" na
"bieżący ChatGPT ma rzeczywiście wywoływalne akcje Jaźni po podłączeniu
persistent runtime". ZIP pozostaje bootstrapem/fallbackiem, ale nie jest już
jedynym projektowanym wejściem.

## Wynik researchu i korekty względem v94

Badanie z 2026-10-01 zostało skonfrontowane z bieżącą dokumentacją OpenAI.

Potwierdzone:

- produkcyjny MCP używa Streamable HTTP pod stabilnym HTTPS endpointem, zwykle
  `/mcp`;
- ChatGPT Developer Mode potrafi podłączyć publiczny endpoint lub Secure MCP
  Tunnel;
- portable Agent Plugin używa root `plugin.json` i `mcp.json`;
- po rejestracji MCP w Developer Mode lokalny/workspace plugin może mapować
  techniczny id aplikacji przez `.app.json`;
- po zmianie nazw/schematów/adnotacji trzeba odświeżyć metadane po stronie
  ChatGPT i testować w nowej rozmowie;
- MCP 2026-07-28 usuwa handshake `initialize` dla modern era i używa
  `server/discover`.

Skorygowane:

- nie dodajemy legacy `ai-plugin.json` ani OpenAPI jako wymaganego manifestu
  nowej ścieżki pluginów;
- sama obecność endpointu/tunelu/plugin package nie jest capability hosta;
- `_meta["openai/visibility"]` jest przestarzałe; model visibility używa
  `_meta.ui.visibility`;
- aliasy `jazn_turn` / `jazn_resume_turn` nie mogą zastępować wymaganego
  kanonicznego ingressu, jeżeli test akceptacyjny oczekuje faktycznych akcji
  `jazn_generate_visible_reply` i `jazn_status`.

## Zmiany kodu

### 1. Kanoniczny model-visible ingress

Modern stdio MCP nie ukrywa już:

- `jazn_generate_visible_reply`;
- `jazn_resume_visible_reply`;
- `jazn_status`;
- `jazn_finalize_reply`.

Dla tych narzędzi `server.py` normalizuje metadata do
`_meta.ui.visibility=["model","app"]` i usuwa legacy
`openai/visibility=private`.

Kompatybilnościowe aliasy Developer Mode pozostają dostępne dla app/UI, ale są
`ui.visibility=["app"]`, żeby nie konkurowały z kanonicznymi narzędziami przy
model selection.

### 2. Publiczny HTTP gateway

Oficjalny MCP Python SDK publikuje teraz bezpośrednio:

- `jazn_generate_visible_reply(request_id, message, session_id?)`;
- `jazn_resume_visible_reply(daemon_request_id, turn_id?,
  host_request_contract_hash?)`;
- `jazn_finalize_reply(...)`;
- `jazn_status()`.

Submit wymaga jawnego `request_id`, dzięki czemu caller nie musi polegać na
niejawnym identyfikatorze wygenerowanym po stronie serwera. Rate limiting i
OAuth scopes są przypisane do kanonicznych nazw.

### 3. Instalowalny package ChatGPT

`chatgpt-plugin-package` nadal generuje portable:

- `plugin.json`;
- `mcp.json`.

Po podaniu `--registered-app-id plugin_asdk_app_...` generuje również:

- `.app.json`;
- `extensions.com.openai.apps="./.app.json"`;
- OpenAI interface metadata w root `plugin.json`.

Id aplikacji jest traktowane jako zewnętrzne evidence uzyskane po rzeczywistej
rejestracji MCP w ChatGPT, a nie jako wartość wymyślana przez repo.

### 4. Persistent runtime

Ta wersja nie przenosi daemonu do sandboxa rozmowy. Obsługiwane topologie
pozostają:

- publiczny HTTPS MCP -> gateway -> loopback daemon;
- Secure MCP Tunnel -> managed `tunnel-client` -> stdio MCP -> loopback daemon.

Dla tunelu preferowana jest natywna ścieżka
`tunnel-client runtimes connect/status/stop`. Gotowość tunelu pozostaje
niewystarczająca bez jawnego host connector/app capability.

## DoD / acceptance

Release jest zaakceptowany dopiero, gdy w nowej rozmowie ChatGPT:

1. lokalny executor może być niedostępny;
2. Jaźń plugin/app jest podłączony i host faktycznie udostępnia callable
   `jazn_status` oraz `jazn_generate_visible_reply`;
3. `jazn_status` potwierdza świeży, zgodny persistent runtime;
4. zwykła wiadomość jest submitowana dokładnie raz z jednym `request_id`;
5. `poll_runtime` prowadzi wyłącznie do resume tego samego
   `daemon_request_id`;
6. `generate_then_finalize` prowadzi do `jazn_finalize_reply`;
7. tekst jest pokazany dopiero dla zaakceptowanego `display_exact` z poprawną
   lineage i MessageEnvelope.

Żaden test repo/CI nie może sam oznaczyć punktów 2–7 jako wykonanych na
konkretnym koncie ChatGPT. CI może dowieść jedynie kontraktu serwera/package.

## Testy regresji

Dodane/zmienione testy sprawdzają:

- obecność kanonicznych nazw w modern `tools/list`;
- model visibility kanonicznych narzędzi i app-only visibility aliasów;
- brak legacy `openai/visibility` na `jazn_status`;
- kanoniczny HTTP submit/resume i zachowanie request identity;
- per-operation rate limit;
- portable plugin package;
- `.app.json` dla zarejestrowanego ChatGPT app id;
- fail-closed walidację endpointu HTTPS i technical app id.

## Źródła

- OpenAI, Build an MCP server:
  https://developers.openai.com/plugins/build/mcp-server
- OpenAI, Package your plugin:
  https://developers.openai.com/plugins/build/plugins
- OpenAI, Connect and test your plugin:
  https://developers.openai.com/plugins/deploy/connect-chatgpt
- OpenAI, Plugin reference:
  https://developers.openai.com/plugins/reference
- OpenAI, Plugin changelog:
  https://developers.openai.com/plugins/changelog
- OpenAI, Authentication:
  https://developers.openai.com/plugins/build/auth
- OpenAI, Secure MCP Tunnel / tunnel-client:
  https://github.com/openai/tunnel-client
- MCP 2026-07-28 release:
  https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

## Granica prawdy

Ta wersja przygotowuje poprawny serwer, package i testowalny kontrakt ingressu.
Nie może z poziomu repozytorium:

- włączyć Developer Mode na koncie;
- utworzyć ChatGPT connection bez działania hosta/użytkownika;
- wygenerować prawdziwego `plugin_asdk_app_...` bez rejestracji;
- zapewnić zewnętrznego hostingu/TLS/IdP;
- udowodnić, że bieżący ChatGPT ma callable Jaźń actions.

Te elementy pozostają wymaganym zewnętrznym testem akceptacyjnym.
