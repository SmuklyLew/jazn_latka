# Secure MCP Tunnel — zdalna trasa ChatGPT do Jaźni

Ten dokument opisuje opcjonalny transport hosta do już istniejącego persistent runtime Jaźni. Nie jest alternatywnym runtime, źródłem tożsamości, pamięcią ani warstwą finalizacji.

## Cel

W zwykłej powierzchni ChatGPT lokalny executor może być niedostępny jeszcze przed utworzeniem procesu. W takim stanie paczka SYSTEM nie może nadać hostowi uprawnień do `python.exe`. Linia 16.3.25.5.73 dodała bezpieczny lokalny cel stdio dla oficjalnego OpenAI Secure MCP Tunnel. Wersja 16.3.25.5.75 domyka brakującą część: trwałe zarządzanie tunelem oraz osobny, jawny gate capability hosta, tak aby gotowość samego procesu tunelu nie była mylona z gotową trasą ChatGPT.

```text
ChatGPT / MCP app capability
        |
        | OpenAI Secure MCP Tunnel
        v
managed tunnel-client runtime
        |
        | stdio
        v
latka_jazn/mcp/tunnel_bootstrap.py
        |
        | verified active_root + daemon identity
        v
JaznMcpServer (stdio JSON-RPC)
        |
        | authenticated loopback only
        v
persistent Jaźń daemon 127.0.0.1:8787
        |
        v
session / memory / cognition / affect / tools / host finalization
```

`latka_jazn/mcp/tunnel_bootstrap.py` uruchamia albo reuse'uje daemon wyłącznie przez istniejący `ensure_daemon_for_runtime_turn(..., explicit_ensure=True)`. MCP nie jest wystawiany, jeżeli runtime/root/endpoint identity nie zostały zweryfikowane.

## Granice prawdy

Rozdzielaj pięć stanów:

1. **package target bundled** — SYSTEM ZIP zawiera `mcp/server.py`, `mcp/secure_tunnel.py` i `mcp/tunnel_bootstrap.py`;
2. **local tunnel target ready** — bootstrap potwierdził persistent daemon i przekazał stdio do istniejącego `JaznMcpServer`;
3. **managed tunnel ready** — zewnętrzny `tunnel-client runtimes status <alias> --json` raportuje łącznie `process_running=true`, `healthy=true`, `ready=true`;
4. **host-usable remote failover ready** — managed tunnel jest gotowy **i** bieżący host ChatGPT jawnie udostępnia odpowiadającą mu connector/app capability;
5. **accepted visible turn** — runtime zakończył właściwą turę przez istniejący kontrakt `generate/resume/finalize` i zwrócił zaakceptowane `display_exact`.

Stan wcześniejszy nigdy nie implikuje automatycznie stanu późniejszego.

## Bezpieczeństwo

- daemon Jaźni nadal nasłuchuje wyłącznie po loopback;
- port 8787 nie jest publikowany do Internetu;
- token daemonu nie opuszcza hosta i jest używany przez `SecureHostRuntimeGateway` lokalnie;
- `tunnel_bootstrap.py` uruchamia MCP po stdio jako proces potomny klienta tunelu;
- stdio parent jest zaufany tylko w tej jawnej trasie Secure MCP Tunnel;
- lista narzędzi, rate limit, idempotency, audyt i host-visible finalization pozostają w istniejącym `JaznMcpServer`/gateway;
- stdout bootstrapu jest wyłącznie kanałem protokołu MCP; diagnostyka idzie na stderr;
- żadnego sekretu control plane nie zapisuje się w repo, paczce ani argumentach procesu Jaźni;
- managed runtime przekazuje klucz przez referencję `env:CONTROL_PLANE_API_KEY`, a nie przez wartość sekretu.

## Wymagania zewnętrzne

Secure MCP Tunnel jest capability hosta/OpenAI, a nie zależnością rdzenia Jaźni. Potrzebne są zewnętrznie:

- oficjalny `tunnel-client` OpenAI;
- identyfikator tunelu (`CONTROL_PLANE_TUNNEL_ID`);
- runtime control-plane API key (`CONTROL_PLANE_API_KEY`);
- dostęp do funkcji custom MCP/app w używanym planie/workspace ChatGPT;
- connector/app wskazujący ten sam tunnel ID.

Brak którejkolwiek z tych rzeczy nie oznacza awarii lokalnego runtime Jaźni.

## Plan tunelu generowany przez Jaźń

Kod buduje platformowo poprawny argv/command przez:

```python
from pathlib import Path
from latka_jazn.mcp.secure_tunnel import build_secure_mcp_tunnel_plan

plan = build_secure_mcp_tunnel_plan(
    Path(r"D:\.AI\jazn_latka_master"),
    tunnel_id="<tunnel-id>",
    runtime_alias="jazn-chatgpt",
)
print(plan.to_dict())
```

### Preferowana ścieżka długotrwała

Aktualny oficjalny `tunnel-client` udostępnia natywne zarządzanie runtime. Dla trwałej trasy failover preferuj:

```text
tunnel-client runtimes connect \
  --alias jazn-chatgpt \
  --tunnel-id <tunnel-id> \
  --runtime-api-key env:CONTROL_PLANE_API_KEY \
  --mcp-command <platformowo-poprawna-komenda-bootstrapu> \
  --json

tunnel-client runtimes status jazn-chatgpt --json
```

Dopiero wynik `status` jest evidence do oceny `process_running`, `healthy` i `ready`. Sam sukces uruchomienia polecenia nie jest dowodem pełnej gotowości.

Zatrzymanie lokalnego supervised runtime, bez usuwania zdalnego tunelu:

```text
tunnel-client runtimes stop jazn-chatgpt --json
```

### Foreground / diagnostyka

Starsza ścieżka profilowa pozostaje wspierana do ręcznego uruchomienia w foreground i diagnostyki:

```text
tunnel-client init --sample sample_mcp_stdio_local --profile jazn-local-runtime --tunnel-id <tunnel-id> --mcp-command <platformowo-poprawna-komenda-bootstrapu>
tunnel-client doctor --profile jazn-local-runtime --explain
tunnel-client run --profile jazn-local-runtime
```

Nie używaj `nohup`, `disown` ani własnej warstwy nadzorującej jako zamiennika natywnego `tunnel-client runtimes connect`.

## Readiness i failover

`classify_tunnel_runtime_status()` klasyfikuje wyłącznie stan managed tunnel runtime. Wszystkie trzy pola muszą być prawdziwe:

```json
{
  "process_running": true,
  "healthy": true,
  "ready": true
}
```

Natomiast `classify_remote_runtime_failover()` jest właściwym gate'em hostowym. Wymaga dodatkowo:

```text
host_connector_capability_available = true
```

Dopiero wtedy evidence może bezpiecznie ustawić:

```text
remote_runtime_transport_available = true
execution_route = remote_runtime
next_action = use_remote_runtime_transport
```

Jeżeli tunel jest gotowy, ale ChatGPT nie udostępnia odpowiadającego connector/app, wynik pozostaje fail-closed z `reason_code=chatgpt_connector_capability_not_verified`.

To nadal nie jest zgoda na pokazanie odpowiedzi. Każda wiadomość przechodzi dalej przez istniejący kontrakt tury i finalizacji.

## Kolejność hosta i negocjacja MCP od v16.3.25.5.81

Secure MCP Tunnel pozostaje jedną z dwóch zdalnych tras transportowych do tego
samego persistent runtime. Drugą jest publiczny, uwierzytelniony Streamable HTTP
MCP. Host nie wybiera trasy na podstawie samej obecności plików, URL-a albo
procesu: dodatni wynik musi pochodzić z właściwego klasyfikatora evidence.

Dla tunelu obowiązuje `classify_remote_runtime_failover()`. Dla publicznego
Streamable HTTP obowiązuje `classify_public_streamable_http_failover()`.
Dodatnie evidence z jednej z tych tras może dopiero ustawić
`remote_runtime_transport_available=true`; wejście JSON do `host-preflight`
nie może już samodzielnie wymusić tej wartości gołym booleanem.

Nowoczesna powierzchnia MCP jest implementowana dla rewizji `2026-07-28`.
`io.modelcontextprotocol/tasks` jest oficjalną extension capability. Jaźń
implementuje trwałe `tasks/get`, `tasks/update` i `tasks/cancel` oraz
`resultType="task"` dla asynchronicznego `jazn_generate_visible_reply`.
`tasks/list` i `tasks/result` nie należą do tej ścieżki. Task jest tworzony
trwale przed zwróceniem handle i zachowuje ten sam `daemon_request_id`, więc
utrata odpowiedzi transportowej prowadzi do poll/resume istniejącego requestu,
a nie do replayu wiadomości.

Paczka używa oficjalnego MCP Python SDK v2 dla rdzenia Streamable HTTP. Ponieważ
przypięta wersja SDK nie dostarcza jeszcze SEP-2663 Tasks, wąski
`ModernTasksHttpBridge` przechwytuje wyłącznie brakującą powierzchnię Tasks;
pozostałe requesty pozostają własnością SDK. Bridge dziedziczy te same granice
uwierzytelnienia, scope, limitów, nagłówków MCP i maksymalnych rozmiarów wejścia.

`poll_runtime` jest stanem bez widocznego tekstu runtime. Może zachować trwałe
wiązanie przez `daemon_request_id` zanim runtime nada pełną lineage.
`generate_then_finalize` i `display_exact` nadal wymagają pełnego związania
bieżącej tury i zaakceptowanej finalizacji.

## Zachowanie przy awarii

- daemon nieaktywny i start nieudany -> MCP nie startuje;
- root/identity daemonu niezgodne -> MCP nie startuje;
- `tunnel-client` nieobecny -> lokalny runtime może działać, remote route pozostaje unverified;
- process running, ale `healthy=false` albo `ready=false` -> remote route pozostaje niedostępna;
- tunnel ready, ale connector/app hosta niezweryfikowany -> remote route pozostaje niedostępna;
- lokalny executor ChatGPT pada przed utworzeniem procesu, ale host ma już zweryfikowany remote failover -> host powinien użyć remote route zamiast ponawiać lokalny bootstrap;
- transport przerwany po submit -> wznowienie istniejącego requestu, nigdy replay wiadomości jako nowej tury;
- finalizacja odrzucona -> host pokazuje diagnostykę, nie własną imitację odpowiedzi Jaźni.

## Ograniczenia powierzchni ChatGPT

Kod Jaźni nie może sam nadać bieżącej powierzchni ChatGPT capability aplikacji,
konektora, zdalnego MCP ani lokalnego executora. Te możliwości są właściwością
hosta i jego aktualnej konfiguracji. Dlatego pozytywna klasyfikacja zdalnej
trasy zawsze wymaga jawnego evidence capability bieżącego hosta, a nie samego
stanu serwera po stronie Jaźni.

Jeżeli host nie udostępnia żadnej zweryfikowanej zdalnej capability i lokalny
executor nie utworzył procesu, właściwym wynikiem pozostaje fail-closed
`host_executor_unavailable` dla tej powierzchni albo jawny host handoff, jeśli
host rzeczywiście go oferuje. Kod runtime nie może imitować brakującej funkcji
produktu.

## Źródła zewnętrzne

- OpenAI Help — Developer mode and MCP apps in ChatGPT: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI Secure MCP Tunnel (`openai/tunnel-client`): https://github.com/openai/tunnel-client
- OpenAI tunnel-client — runtime flows: https://github.com/openai/tunnel-client/blob/master/plugins/tunnel-mcp/skills/tunnel-mcp/references/runtime-flows.md
- OpenAI tunnel-client — permissions and ChatGPT connector setup: https://github.com/openai/tunnel-client/blob/master/docs/permissions.md
- OpenAI Help — ChatGPT Work and Codex: https://help.openai.com/en/articles/20001275
- Model Context Protocol — SEP-2663 Tasks extension: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2663-tasks-extension.md
- Model Context Protocol — SEP-2243 HTTP standardization: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2243-http-standardization.md
- MCP Python SDK v2.2.0 release notes: https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0
