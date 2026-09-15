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

## Kolejność hosta i negocjacja MCP od v16.3.25.5.76.1

Jeżeli host ma już zweryfikowaną trasę `remote_runtime`, agregator capability wybiera ją przed lokalnym bootstrapem. Lokalny executor pozostaje trasą bootstrap/recovery, ale nie może przejąć zwykłej tury tylko dlatego, że jest chwilowo dostępny, gdy równocześnie istnieje mocniejszy, jawnie zweryfikowany connector do persistent runtime.

Serwer MCP negocjuje obecnie jawnie wersje `2025-11-25` i `2025-06-18`. Nieznana wersja klienta nie jest bezwarunkowo echo-wana; serwer odpowiada najnowszą wspieraną wersją. Dla `2025-11-25` serwer reklamuje standardowe `tools`, ale **nie reklamuje standardowego MCP Tasks**, dopóki nie implementuje kompletnego kontraktu `tasks/list`, `tasks/get`, `tasks/result`, `tasks/cancel`, standardowych obiektów task i semantyki terminalnego anulowania. Istniejący `jazn_resume_visible_reply` pozostaje kanoniczną, idempotentną ścieżką trwałego poll/resume. Starszy adapter `io.modelcontextprotocol/tasks` pozostaje ograniczonym compatibility path wyłącznie dla negocjowanego `2025-06-18`; nie jest deklaracją zgodności z Tasks 2025-11-25.

`poll_runtime` jest stanem bez widocznego tekstu runtime. Może więc zachować trwałe wiązanie przez `daemon_request_id` zanim runtime nada `turn_id/trace_id`. `generate_then_finalize` i `display_exact` nadal wymagają silnego związania bieżącej tury i nie dziedziczą tego wyjątku.

## Zachowanie przy awarii

- daemon nieaktywny i start nieudany -> MCP nie startuje;
- root/identity daemonu niezgodne -> MCP nie startuje;
- `tunnel-client` nieobecny -> lokalny runtime może działać, remote route pozostaje unverified;
- process running, ale `healthy=false` albo `ready=false` -> remote route pozostaje niedostępna;
- tunnel ready, ale connector/app hosta niezweryfikowany -> remote route pozostaje niedostępna;
- lokalny executor ChatGPT pada przed utworzeniem procesu, ale host ma już zweryfikowany remote failover -> host powinien użyć remote route zamiast ponawiać lokalny bootstrap;
- transport przerwany po submit -> wznowienie istniejącego requestu, nigdy replay wiadomości jako nowej tury;
- finalizacja odrzucona -> host pokazuje diagnostykę, nie własną imitację odpowiedzi Jaźni.

## Ograniczenia planu i powierzchni ChatGPT

Kod Jaźni nie może sam włączyć custom MCP/app na koncie ChatGPT ani zmienić uprawnień planu. Według aktualnej dokumentacji OpenAI pełna obsługa MCP jest dostępna w Business i Enterprise/Edu; Pro ma ograniczony dostęp read/fetch w Developer Mode. Osobisty Plus nie otrzymuje przez sam kod Jaźni prawa do utworzenia custom MCP app.

Dlatego linia 16.3.25.5.75–76.1 naprawia **mechanizm systemowy i truth boundary**, ale nie udaje, że paczka Python może zmienić funkcje produktu ChatGPT. Jeśli bieżąca powierzchnia nie ma custom MCP/app, poprawną alternatywą jest host handoff do powierzchni, która rzeczywiście posiada executor, np. lokalny Work/Codex w aplikacji desktopowej, jeżeli jest dostępny na koncie i otrzymał wymagane uprawnienia.

## Źródła zewnętrzne

- OpenAI Help — Developer mode and MCP apps in ChatGPT: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI Secure MCP Tunnel (`openai/tunnel-client`): https://github.com/openai/tunnel-client
- OpenAI tunnel-client — runtime flows: https://github.com/openai/tunnel-client/blob/master/plugins/tunnel-mcp/skills/tunnel-mcp/references/runtime-flows.md
- OpenAI tunnel-client — permissions and ChatGPT connector setup: https://github.com/openai/tunnel-client/blob/master/docs/permissions.md
- OpenAI Help — ChatGPT Work and Codex: https://help.openai.com/en/articles/20001275
- Model Context Protocol 2025-11-25 — Lifecycle/version & capability negotiation: https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- Model Context Protocol 2025-11-25 — Tasks: https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks
