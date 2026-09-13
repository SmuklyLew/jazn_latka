# Jaźń v16.3.25.5.73 — Secure MCP Tunnel runtime bridge convergence

## Problem

Wersja 16.3.25.5.72 poprawnie rozdzieliła trzy topologie wykonawcze ChatGPT: lokalny executor, zewnętrzny remote runtime i host handoff. Pozostawała jednak luka wykonawcza: SYSTEM package deklarował `remote_runtime_external`, lecz nie dostarczał kanonicznego lokalnego celu, który oficjalny zewnętrzny transport ChatGPT mógł bezpiecznie połączyć z istniejącym persistent runtime Jaźni.

Jednocześnie repozytorium miało już prywatny `JaznMcpServer` po stdio, `SecureHostRuntimeGateway`, daemonowy chat/result/finalization lifecycle, audyt i idempotency. Budowanie drugiej logiki MCP/HTTP oznaczałoby rozszczepienie odpowiedzialności i ryzyko obejścia istniejącej tury/finalizacji.

## Evidence zewnętrzne

Implementacja opiera się na aktualnych granicach hosta i oficjalnym transporcie:

- OpenAI Help, **Developer mode and MCP apps in ChatGPT** — lokalny/prywatny serwer MCP nie jest po prostu `localhost` widocznym dla webowego ChatGPT; wymagany jest wspierany zdalny transport/connector, a dostęp zależy od planu/workspace:
  https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI, **Secure MCP Tunnel (`openai/tunnel-client`)** — klient uruchamia lokalny serwer MCP po stdio i łączy go wychodząco z control plane bez publicznego inbound portu; profil `sample_mcp_stdio_local` przyjmuje `--mcp-command`:
  https://github.com/openai/tunnel-client
- Model Context Protocol, **Transports** — stdio oznacza proces potomny klienta z komunikacją stdin/stdout, natomiast Streamable HTTP jest osobną topologią. Nie należy ich mieszać ani udawać, że zwykły web host tworzy lokalny proces:
  https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- OpenAI Help, **ChatGPT Work and Codex** — dostęp do lokalnych plików/terminala jest capability właściwej powierzchni wykonawczej, a nie uprawnieniem nadawanym przez paczkę Python:
  https://help.openai.com/en/articles/20001275

## Decyzja architektoniczna

Nie dodano nowego serwera HTTP ani nowej zewnętrznej zależności Pythona. Oficjalny Secure MCP Tunnel potrafi uruchomić istniejący stdio MCP, więc zachowano jednego właściciela semantyki narzędzi:

```text
OpenAI Secure MCP Tunnel
  -> latka_jazn/mcp/tunnel_bootstrap.py
     -> ensure/reuse verified persistent daemon
     -> JaznMcpServer.serve_stdio()
        -> SecureHostRuntimeGateway
           -> daemon /chat, /chat-result, /chat-finalization
              -> ten sam runtime / memory / cognition / affect / finalization
```

Transport nie otrzymuje własnej pamięci, osobowości, routingu ani finalizacji. Jest odpowiednikiem drogi nerwowej do istniejącego systemu, nie drugim systemem.

## Zmiany kodu

### `latka_jazn/mcp/secure_tunnel.py`

Nowy kontrakt transportu:

- generuje platformowo poprawny stdio argv/command dla Windows/POSIX;
- buduje oficjalny profil `tunnel-client init --sample sample_mcp_stdio_local`;
- publikuje `doctor` i `run` argv bez osadzania sekretów;
- wykrywa lokalną dostępność `tunnel-client` bez instalowania go;
- klasyfikuje managed tunnel jako remote-ready wyłącznie przy `process_running=true`, `healthy=true`, `ready=true`;
- rozdziela `package_contains_tunnel_target` od `remote_runtime_transport_bundled`.

### `latka_jazn/mcp/tunnel_bootstrap.py`

Nowy bezpieczny stdio target:

1. używa istniejącego `ensure_daemon_for_runtime_turn(... explicit_ensure=True)`;
2. wymaga `ok`, `ensured` oraz `daemon_identity_verified`;
3. przechodzi na zweryfikowany `resolved_active_root` zamiast zakładać requested root;
4. przy braku readiness kończy się fail-closed przed uruchomieniem MCP;
5. przy sukcesie przekazuje protokół do istniejącego `JaznMcpServer` z jawnie zaufanym stdio parent dla Secure MCP Tunnel;
6. diagnostykę zapisuje wyłącznie do stderr; stdout pozostaje protokołem MCP.

### `latka_jazn/core/bridge_discovery.py`

Discovery publikuje teraz:

- `remote_transport = openai_secure_mcp_tunnel`;
- plan tunelu oraz stan lokalnego klienta;
- wymagane pola readiness;
- jawne rozdzielenie właścicieli identity/memory/turn od transportu;
- `external_tunnel_control_plane_bundled=false`.

### `tools/jazn_pack_generator_app/manifest.py`

Host bootstrap contract zachowuje prawdę:

- `remote_runtime_transport_bundled=false` — OpenAI tunnel client/control plane pozostaje zewnętrzny;
- `secure_mcp_tunnel_target_bundled=true` tylko jeśli komplet trzech lokalnych plików MCP rzeczywiście jest w package;
- remote readiness wymaga zewnętrznego klienta, uwierzytelnionego control plane, pełnego managed readiness i hostowego connector/app capability.

### `latka_jazn/version.py`

Wersja systemu: `16.3.25.5.73-secure-mcp-tunnel-runtime-bridge-convergence`.

## Testy regresyjne

Dodano nowe, aktywne testy bez modyfikowania historycznych snapshotów:

- `tests/test_secure_mcp_tunnel_contract.py`
  - Windows/POSIX quoting;
  - brak publicznego inbound listenera;
  - fail-closed readiness;
  - remote route dopiero po pełnym readiness.
- `tests/test_secure_mcp_tunnel_bootstrap.py`
  - reuse aktywnego subject root;
  - blokada przy niezweryfikowanej identity;
  - brak startu MCP po nieudanym bootstrapie;
  - delegacja do istniejącego `JaznMcpServer` dopiero po readiness.
- `tests/test_pack_generator_secure_mcp_bridge_contract.py`
  - komplet lokalnego targetu vs niekompletny target;
  - brak fałszywego twierdzenia, że external transport jest bundled.

Pełny wynik testów i CI jest evidence GitHub Actions dla PR; nie jest deklarowany przed faktycznym zakończeniem workflow.

### Test Studio governance

Pierwszy CI wykazał, że nowe aktywne testy nie miały jeszcze rekordów `purpose`/`expected` w `tools/jazn_tests_studio/test_contracts.json`. Gate nie został osłabiony. Dodano `tools/jazn_tests_studio/sync_contract_catalog.py`, który korzysta z istniejącego deterministycznego AST buildera `build_contract_catalog()` i stempluje bieżący `PACKAGE_VERSION`.

Workflow `stable-test-contracts.yml`:

- na branchach aktualizacyjnych synchronizuje wyłącznie `test_contracts.json` i odmawia auto-commitu przy jakimkolwiek innym dirty path;
- na walidacji wykonuje `sync_contract_catalog.py --check` przed właściwym governance testem;
- utrzymuje zasadę, że każdy aktywny test ma jawny, niepusty kontrakt celu i oczekiwania.

## Model bezpieczeństwa

- port daemonu 8787 pozostaje loopback-only;
- daemon token pozostaje lokalny;
- nie powstaje publiczny serwer Jaźni;
- tunnel-client jest zewnętrznym procesem hosta i nie trafia do Python core dependencies;
- control-plane secrets nie trafiają do repo ani package;
- utrata tunelu nie powoduje lokalnego replayu wiadomości;
- PID/heartbeat/tunnel-ready nie są accepted visible turn;
- widoczny tekst nadal wymaga kanonicznego host-visible finalization.

## Ograniczenie platformowe

Ta aktualizacja dostarcza poprawny systemowy endpoint dla Secure MCP Tunnel, ale nie może programowo nadać kontu ChatGPT funkcji custom MCP. Dostępność custom MCP/Developer Mode jest kontrolowana przez OpenAI i zależy od planu/workspace/rolloutu. Jeżeli bieżący host nie ma tej capability, kod poprawnie pozostaje przy `host_handoff` lub lokalnej trasie wykonawczej zamiast fałszywie deklarować `remote_runtime`.

## Kryterium gotowości do merge

Branch może być uznany za merge-ready dopiero po:

1. synchronizacji release metadata przez kanoniczny workflow;
2. zielonych wymaganych testach Python/CI;
3. braku konfliktu z aktualnym `master`;
4. pozytywnym GitHub mergeability;
5. braku nierozwiązanych wymaganych review/check failures.
