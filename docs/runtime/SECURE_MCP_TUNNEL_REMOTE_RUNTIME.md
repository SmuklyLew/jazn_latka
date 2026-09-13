# Secure MCP Tunnel — zdalna trasa ChatGPT do Jaźni

Ten dokument opisuje opcjonalny transport hosta do już istniejącego persistent runtime Jaźni. Nie jest alternatywnym runtime, źródłem tożsamości, pamięcią ani warstwą finalizacji.

## Cel

W zwykłej powierzchni ChatGPT lokalny executor może być niedostępny jeszcze przed utworzeniem procesu. W takim stanie paczka SYSTEM nie może nadać hostowi uprawnień do `python.exe`. Wersja 16.3.25.5.73 dodaje dlatego bezpieczny lokalny cel stdio dla oficjalnego OpenAI Secure MCP Tunnel:

```text
ChatGPT / MCP app capability
        |
        | OpenAI Secure MCP Tunnel
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

Rozdzielaj cztery stany:

1. **package target bundled** — SYSTEM ZIP zawiera `mcp/server.py`, `mcp/secure_tunnel.py` i `mcp/tunnel_bootstrap.py`;
2. **local tunnel target ready** — bootstrap potwierdził persistent daemon i przekazał stdio do istniejącego `JaznMcpServer`;
3. **remote tunnel ready** — zewnętrzny `tunnel-client` raportuje łącznie `process_running=true`, `healthy=true`, `ready=true`, a host ma jawnie dostępny connector/app capability;
4. **accepted visible turn** — runtime zakończył właściwą turę przez istniejący kontrakt `generate/resume/finalize` i zwrócił zaakceptowane `display_exact`.

Stan wcześniejszy nigdy nie implikuje automatycznie stanu późniejszego.

## Bezpieczeństwo

- daemon Jaźni nadal nasłuchuje wyłącznie po loopback;
- port 8787 nie jest publikowany do Internetu;
- token daemonu nie opuszcza hosta i jest używany przez `SecureHostRuntimeGateway` lokalnie;
- `tunnel_bootstrap.py` uruchamia MCP po stdio jako proces potomny klienta tunelu;
- stdio parent jest zaufany tylko w tej jawnej trasie Secure MCP Tunnel;
- lista narzędzi, rate limit, idempotency, audyt i host-visible finalization pozostają w istniejącym `JaznMcpServer`/gateway;
- stdout bootstrapu jest wyłącznie kanałem protokołu MCP; diagnostyka idzie na stderr;
- żadnego sekretu control plane nie zapisuje się w repo, paczce ani konfiguracji Jaźni.

## Wymagania zewnętrzne

Secure MCP Tunnel jest capability hosta/OpenAI, a nie zależnością rdzenia Jaźni. Potrzebne są zewnętrznie:

- oficjalny `tunnel-client` OpenAI;
- identyfikator tunelu (`CONTROL_PLANE_TUNNEL_ID`);
- control-plane API key (`CONTROL_PLANE_API_KEY`);
- dostęp do funkcji custom MCP/app w używanym planie/workspace ChatGPT.

Brak którejkolwiek z tych rzeczy nie oznacza awarii lokalnego runtime Jaźni.

## Budowa profilu tunelu

Kod potrafi zbudować platformowo poprawny argv/command przez:

```python
from pathlib import Path
from latka_jazn.mcp.secure_tunnel import build_secure_mcp_tunnel_plan

plan = build_secure_mcp_tunnel_plan(Path(r"D:\.AI\jazn_latka_master"), tunnel_id="<tunnel-id>")
print(plan.to_dict())
```

Plan odpowiada oficjalnej trasie stdio `sample_mcp_stdio_local` i generuje trzy polecenia operatorskie:

```text
tunnel-client init --sample sample_mcp_stdio_local --profile jazn-local-runtime --tunnel-id <tunnel-id> --mcp-command <platformowo-poprawna-komenda-bootstrapu>
tunnel-client doctor --profile jazn-local-runtime --explain
tunnel-client run --profile jazn-local-runtime
```

Nie wklejaj klucza control plane do argumentów polecenia. Przekaż go przez wspierany mechanizm środowiska/sekretów klienta tunelu.

## Readiness

`latka_jazn.mcp.secure_tunnel.classify_tunnel_runtime_status()` uznaje transport zdalny za dostępny wyłącznie, gdy wszystkie trzy oficjalne pola managed-runtime są prawdziwe:

```json
{
  "process_running": true,
  "healthy": true,
  "ready": true
}
```

Dopiero wtedy evidence może ustawić:

```text
remote_runtime_transport_available = true
execution_route = remote_runtime
next_action = use_remote_runtime_transport
```

To nadal nie jest zgoda na pokazanie odpowiedzi. Każda wiadomość przechodzi dalej przez istniejący kontrakt tury i finalizacji.

## Zachowanie przy awarii

- daemon nieaktywny i start nieudany -> MCP nie startuje;
- root/identity daemonu niezgodne -> MCP nie startuje;
- `tunnel-client` nieobecny -> lokalny runtime może działać, remote route pozostaje unverified;
- tunnel running, ale `healthy=false` albo `ready=false` -> remote route pozostaje niedostępna;
- transport przerwany po submit -> wznowienie istniejącego requestu, nigdy replay wiadomości jako nowej tury;
- finalizacja odrzucona -> host pokazuje diagnostykę, nie własną imitację odpowiedzi Jaźni.

## Ograniczenie platformowe ChatGPT

Kod Jaźni nie może sam włączyć funkcji custom MCP na koncie ChatGPT. Dostępność Developer Mode/MCP zależy od aktualnego planu, workspace i rolloutów OpenAI. Gdy bieżący host nie udostępnia custom MCP, właściwą trasą pozostaje `host_handoff` do wykonawczej powierzchni desktop/Work/Codex albo lokalny klient obsługujący transport.

## Źródła zewnętrzne

- OpenAI Help — Developer mode and MCP apps in ChatGPT: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI Secure MCP Tunnel (`openai/tunnel-client`): https://github.com/openai/tunnel-client
- Model Context Protocol — Transports: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- OpenAI Help — ChatGPT Work and Codex: https://help.openai.com/en/articles/20001275
