# ChatGPT Remote-only Ingress — v127.30.10

> **Aktualny kontrakt docelowy v127.30.10 (J-012).** Przywrócono remote-only zgodnie z korektą operatora z 2026-11-24. Historyczna polityka `hybrid_adaptive` v114/v115 pozostaje w `CHATGPT_HYBRID_ADAPTIVE_INGRESS.md` wyłącznie jako referencja migracyjna. Implementacja i rzeczywisty odbiór są odrębnymi dowodami; zob. `../project/releases/v127.30.10/IMPLEMENTATION_PROGRESS.md`.

## Cel

Zwykła rozmowa ChatGPT nie może zależeć od tego, czy efemeryczny host dostał
lokalny/process executor. Jedyną normalną ścieżką jest aplikacja/MCP, która
łączy bieżącą wiadomość z jednym persistent runtime Jaźni.

## Normalny przepływ

```text
ChatGPT current message
  -> current callable Jaźń app/toolset
  -> jazn_status
  -> verified persistent runtime
  -> jazn_generate_visible_reply(request_id, message)
  -> jazn_resume_visible_reply(same request) when required
  -> jazn_finalize_reply
  -> accepted display_exact
```

W ordinary-chat nie wykonuje się `container.exec`, `python.exec`, terminala,
discovery SYSTEM/MEMORY, materializacji, bootstrapu, startu daemona ani host handoffu jako fallbacku. Brak zweryfikowanej trasy daje `host_diagnostic` bez imitacji Jaźni. Wymagana jest weryfikacja auth, instancji, wersji, kontraktu, readiness i świeżego heartbeat.

## Wymagany toolset

Bieżąca wiadomość musi rzeczywiście wystawiać:
- `jazn_status`;
- `jazn_generate_visible_reply`;
- `jazn_resume_visible_reply`;
- `jazn_finalize_reply`.

`chatgpt_toolset.py` publikuje `jazn_chatgpt_turn_toolset/v2` oraz SHA-256
kanonicznej listy. `jazn_status` przekazuje ten fingerprint w redacted statusie.

## Frozen/stale app snapshot

Zmiana definicji MCP po stronie serwera nie dowodzi, że ChatGPT używa nowego
toolsetu. Jeżeli bieżąca aplikacja nie wystawia kompletnej kanonicznej
powierzchni, wynik jest fail-closed. Operator powinien wykonać Refresh albo
Recreate/republish zgodnie z możliwościami bieżącego workspace. Nie próbuj
uzupełniać brakującego narzędzia executorem.

## Transport

Dopuszczalne produkcyjne transporty prowadzą do tego samego persistent runtime:

1. publiczny HTTPS MCP / Streamable HTTP;
2. OpenAI Secure MCP Tunnel dla prywatnego/lokalnego MCP;
3. `registered_mcp_app` — istniejące zarejestrowane powiązanie aplikacji, wymagające faktycznego wywołania i świeżego statusu, nie osobny runtime.

Preferowana produkcyjna trasa publiczna: autoryzowany HTTPS MCP przez stabilny Cloudflare Named Tunnel do gatewaya, bez publicznego wystawiania prywatnego daemona lub MEMORY.

Secure MCP Tunnel nie wymaga publicznego inbound listenera MCP, ale wymaga
konfiguracji tunelu, runtime API key oraz odpowiednich uprawnień organizacji /
workspace. Publiczny plugin wymaga stabilnego publicznie osiągalnego HTTPS MCP.

## Message-scoped exposure

Kod Jaźni nie może sam przypiąć aplikacji do każdej przyszłej wiadomości.
ChatGPT musi faktycznie wystawić aplikację/toolset dla bieżącej wiadomości.
Brak takiej ekspozycji pozostaje blockerem platformy i nie uruchamia
`operator_recovery`.

## Operator recovery

`operator_recovery` jest jawnie wybieranym trybem serwisowym dla
Work/Codex/lokalnego operatora lub użytkownika proszącego o recovery. Dopiero
tam wolno używać local executora, filesystemu, SYSTEM ZIP-a i bootstrapu.
Nigdy nie jest to automatyczny fallback ordinary-chat.

## Kryteria akceptacji

Release jest zgodny z tym kontraktem, gdy:
- działający local executor bez remote app NIE staje się route'em ordinary-chat;
- verified remote app staje się `execution_route=remote_runtime`;
- brak toolsetu daje fail-closed, a nie probe executora;
- retry po niejednoznacznym submit używa tego samego request_id i resume;
- widoczna odpowiedź wymaga zaakceptowanego `display_exact`;
- po zmianie tool surface operator wykonuje Refresh/Recreate/republish i testuje
  nową rozmowę.

## Źródła OpenAI zweryfikowane dla tej aktualizacji

- https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/api/docs/guides/custom-mcp-server
- https://developers.openai.com/api/docs/guides/tools-connectors-mcp
