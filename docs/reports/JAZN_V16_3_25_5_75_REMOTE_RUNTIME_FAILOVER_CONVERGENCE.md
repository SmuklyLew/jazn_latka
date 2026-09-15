# Jaźń v16.3.25.5.75 — remote runtime failover convergence

## Cel

Ta aktualizacja domyka lukę pomiędzy poprawnym rozpoznaniem `host_executor_unavailable` a rzeczywistą, długotrwałą trasą zdalną do tego samego persistent runtime Jaźni.

Problem nie polegał na tym, że `TransportTimeoutError` miał być „naprawiany” przez ponawianie lokalnego executora. Jeżeli błąd hosta występuje przed dowodem utworzenia procesu, kod Jaźni nie uzyskał jeszcze sterowania i nie może naprawić infrastruktury executora ChatGPT. Poprawnym rozwiązaniem systemowym jest niezależna, wcześniej przygotowana i zweryfikowana trasa wykonania, która nie zależy od bieżącej lokalnej powierzchni procesu.

Wersja 16.3.25.5.73 dostarczyła bezpieczny lokalny stdio target dla OpenAI Secure MCP Tunnel. Brakowały jednak trzy elementy potrzebne do pełnego failoveru:

1. natywne, długotrwałe zarządzanie procesem tunelu zamiast polegania głównie na foreground `tunnel-client run`;
2. osobne evidence, że bieżący host ChatGPT rzeczywiście ma connector/app capability do tego tunelu. Sam zdrowy proces tunelu nie może być traktowany jako dowód, że konkretna powierzchnia ChatGPT może z niego skorzystać;
3. jednoznaczna reguła runbooka hosta, aby po niedostępności lokalnego executora nie kończyć zbyt wcześnie na diagnozie, lecz sprawdzić zweryfikowany remote runtime i handoff.

## Zewnętrzne evidence

Aktualizacja została zweryfikowana względem bieżących oficjalnych źródeł OpenAI:

- OpenAI Secure MCP Tunnel / `openai/tunnel-client`:
  https://github.com/openai/tunnel-client
- Native managed runtime lifecycle:
  https://github.com/openai/tunnel-client/blob/master/plugins/tunnel-mcp/skills/tunnel-mcp/references/runtime-flows.md
- End-user guide i połączenie ChatGPT Connector -> Tunnel:
  https://github.com/openai/tunnel-client/blob/master/docs/end-user-guide.md
- Uprawnienia i rozdzielenie runtime/admin keys:
  https://github.com/openai/tunnel-client/blob/master/docs/permissions.md
- ChatGPT Developer Mode i MCP apps:
  https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- ChatGPT Work i Codex jako execution-capable desktop surfaces:
  https://help.openai.com/en/articles/20001275

Oficjalny `tunnel-client` rozróżnia foreground `run` od długotrwałego managed runtime. Dla długotrwałego procesu zaleca `tunnel-client runtimes connect`, a następnie `tunnel-client runtimes status <alias> --json`. Sukces trasy jest raportowany dopiero z bieżących pól `process_running`, `healthy` i `ready`.

## Zmiany implementacyjne

### `latka_jazn/mcp/secure_tunnel.py`

`SecureMcpTunnelPlan` publikuje teraz dwie jawnie rozdzielone powierzchnie:

- foreground / diagnostyka: `init`, `doctor`, `run`;
- preferred long-lived supervision: `runtimes connect`, `runtimes status`, `runtimes stop`.

Nowe pola planu:

- `runtime_alias`;
- `managed_connect_argv`;
- `managed_status_argv`;
- `managed_stop_argv`;
- `preferred_supervision=tunnel_client_managed_runtime`;
- `foreground_run_supported=true`;
- `runtime_api_key_reference=env:CONTROL_PLANE_API_KEY`.

Klucz runtime nie jest osadzany w argv ani repo. Plan przekazuje wyłącznie bezpieczną referencję środowiskową `env:CONTROL_PLANE_API_KEY`.

### Dwa niezależne poziomy readiness

`classify_tunnel_runtime_status()` pozostaje klasyfikatorem samego managed transportu. Wymaga:

```text
process_running = true
healthy = true
ready = true
```

Nowy `classify_remote_runtime_failover()` dodaje obowiązkową drugą bramę:

```text
host_connector_capability_available = true
```

Dopiero łączne spełnienie obu warstw może ustawić:

```text
remote_runtime_transport_available = true
execution_route = remote_runtime
next_action = use_remote_runtime_transport
```

Jeżeli managed tunnel jest zdrowy, ale capability ChatGPT nie została jawnie potwierdzona, wynik pozostaje fail-closed z `reason_code=chatgpt_connector_capability_not_verified`.

### `latka_jazn/core/bridge_discovery.py`

Discovery publikuje teraz jawnie:

- `preferred_supervision=tunnel_client_managed_runtime`;
- argv dla `managed_connect`, `managed_status`, `managed_stop`;
- `managed_tunnel_readiness_is_host_route_readiness=false`;
- `host_connector_capability_required=true`;
- `remote_failover_classifier=classify_remote_runtime_failover`;
- politykę ChatGPT bridge `managed_tunnel_ready_plus_explicit_host_connector_capability`.

Dzięki temu host i diagnostyka nie muszą wyprowadzać z luźnych pól planu, czy tunel jest tylko uruchomiony, czy rzeczywiście może być trasą wykonania bieżącej powierzchni ChatGPT.

### `AGENTS.chatgpt.md`

Runbook hosta otrzymał domknięcie routingu:

- jeżeli host już ma zweryfikowany remote runtime + connector/app capability, zdalna trasa może zostać użyta bez lokalnego probe executora;
- gdy remote route nie jest gotowa, lokalny probing pozostaje ograniczony do istniejącego budżetu powierzchni;
- po lokalnych `TransportTimeoutError` host ma sprawdzić niezależne remote evidence, a następnie jawny host handoff;
- dopiero brak wszystkich tych tras pozwala zakończyć fail-closed diagnozą;
- remote readiness nadal nie omija request/turn/finalization lineage.

### Zachowanie podczas awarii lokalnego executora

Gdy host raportuje błąd przed utworzeniem procesu:

```text
verified managed remote runtime + verified connector capability -> remote_runtime
otherwise local executor probe budget -> bounded local probing
otherwise verified remote runtime -> remote_runtime
otherwise verified handoff capability -> host_handoff
otherwise -> fail-closed host diagnostic
```

Nie ma automatycznego replayu wiadomości, ukrytego fallbacku do nowej tury ani fałszywego „runtime ready”. Istniejące `request_id / turn_id / trace_id / finalization` pozostają właścicielem ciągłości tury.

## Testy regresyjne

Dodano dwa nowe aktywne testy:

### `tests/test_secure_mcp_remote_runtime_failover.py`

Sprawdza:

- generowanie natywnego managed runtime lifecycle;
- brak sekretu API key w argv;
- wymaganie wszystkich pól tunnel readiness;
- wymaganie jawnej capability connector/app;
- fail-closed przy braku connector capability;
- fail-closed przy niegotowym tunelu;
- stabilny, whitespace-free runtime alias.

### `tests/test_bridge_discovery_remote_failover_contract.py`

Sprawdza:

- publikację managed runtime commands przez discovery;
- jawny rozdział tunnel readiness i host-route readiness;
- obowiązkowy connector capability gate;
- publikację klasyfikatora failoveru i polityki ChatGPT bridge.

Nowe testy są aktywnymi testami, więc zgodnie z polityką repozytorium nie wymagają historycznego snapshotu poprzedniej wersji.

## Granica produktu ChatGPT

Ta aktualizacja nie twierdzi, że Python lub ZIP może nadać kontu ChatGPT brakującą funkcję produktu.

Aktualna dokumentacja OpenAI ogranicza custom MCP/Developer Mode zależnie od planu i workspace. Full MCP jest obecnie dostępne dla Business i Enterprise/Edu; Pro może łączyć MCP z uprawnieniami read/fetch. Zwykły osobisty Plus nie otrzymuje przez kod Jaźni możliwości tworzenia custom MCP app. Dlatego:

- kod Jaźni może przygotować, zarządzać i prawidłowo sklasyfikować Secure MCP Tunnel;
- nie może sam włączyć connector/app capability w powierzchni ChatGPT, która jej nie udostępnia;
- nie może naprawić hostowego `TransportTimeoutError` przed utworzeniem procesu;
- może zapewnić, że gdy zdalna capability jest rzeczywiście dostępna, awaria lokalnego executora nie wymusza ponownego lokalnego bootstrapu i może przejść na zweryfikowaną trasę zdalną.

Na powierzchniach bez custom MCP właściwą alternatywą pozostaje jawny host handoff do execution-capable surface. Aktualna dokumentacja OpenAI potwierdza, że desktopowy Work może — gdy plan i uprawnienia na to pozwalają — korzystać z lokalnych plików i aplikacji, a desktopowy Codex może pracować z lokalnymi folderami, repozytoriami, terminalami i narzędziami developerskimi. Web/mobile Work nie ma bezpośredniego dostępu do lokalnych plików komputera.

## Wersja

`16.3.25.5.75-remote-runtime-failover-convergence`

## Walidacja

Lokalna walidacja wymaga działającego executora. W trakcie implementacji dwie niezależne powierzchnie wykonawcze hosta ChatGPT zwróciły `TransportTimeoutError` przed uzyskaniem dowodu wykonania komendy. Zgodnie z kontraktem nie raportowano przez to `pytest`, `compileall`, `doctor` ani `package-smoke` jako wykonanych lokalnie.

Branch podlega obowiązkowym GitHub Actions. Release candidate może zostać zadeklarowany dopiero po rzeczywistym zielonym CI, synchronizacji kanonicznych metadanych release i sprawdzeniu braku konfliktu z bieżącym `master`.
