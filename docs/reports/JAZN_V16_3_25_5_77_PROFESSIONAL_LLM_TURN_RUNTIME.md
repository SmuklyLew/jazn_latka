# Jaźń v16.3.25.5.77 — professional LLM turn runtime

## Cel

Aktualizacja porządkuje rozmowę ChatGPT/MCP bez tworzenia drugiego runtime i bez przenoszenia lifecycle z `main.py`. Główne zmiany są kodowe: jeden typed turn runtime, dual-era MCP 2026/legacy oraz twardsza polityka wejścia do modelu.

## Zmiany kodu

- `latka_jazn/runtime/turn_runtime.py`
  - `ExecutionRoute`, `TurnAction`, `TurnPhase` i jawna tabela legalnych przejść;
  - stabilny `request_id`, fingerprint wiadomości i transportowy `traceparent`;
  - remote-first routing tylko przy łącznym dowodzie `process_running + healthy + ready + host connector capability`;
  - fail-closed walidacja `display_exact`, `generate_then_finalize` i `poll_runtime`;
  - side-effecting submit nigdy nie jest automatycznie replayowany; recovery używa tego samego requestu.
- `latka_jazn/mcp/turn_runtime_adapter.py`
  - wiąże oczekiwaną tożsamość requestu z JSON-RPC/MCP przed zaufaniem odpowiedzi;
  - mismatch request identity kończy turę `host_diagnostic` zamiast kontynuacji niespójnego stanu;
  - dołącza typed directive, retry semantics i trace correlation do prywatnego `_meta`.
- `latka_jazn/mcp/server.py`
  - obsługuje stateless MCP `2026-07-28` oraz zachowuje legacy `initialize` dla starszych klientów;
  - implementuje `server/discover`, wymagane per-request `_meta`, `resultType`, `serverInfo`, deterministic `tools/list` oraz cache hints;
  - `initialize` nigdy nie negocjuje handshake-free `2026-07-28`, tylko najnowszą wspieraną wersję legacy;
  - nie reklamuje `io.modelcontextprotocol/tasks`, dopóki współczesny kontrakt rozszerzenia nie jest kompletny;
  - nadal deleguje wykonanie tooli, auth, idempotency i finalization do jednego istniejącego runtime.
- `latka_jazn/model_adapters/base.py`, `openai_responses_adapter.py`, `core/runtime_turn_contract.py`
  - oddzielają stabilny kanon od dynamicznego kontekstu tury i umieszczają aktualną wiadomość na końcu promptu;
  - wyprowadzają `prompt_cache_key` wyłącznie z immutable canon hash, bez danych użytkownika;
  - dodają runtime-owned `allowed_tool_names`; model nie może rozszerzyć listy tooli;
  - konflikt lub nazwa spoza zadeklarowanych narzędzi kończy się fail-closed.

## Aktualny MCP 2026-07-28

MCP `2026-07-28` usuwa protokołową sesję oraz `initialize/initialized` z nowej ery. Każdy request niesie `io.modelcontextprotocol/protocolVersion` i `io.modelcontextprotocol/clientCapabilities` w `_meta`; `server/discover` służy do discovery i jest obowiązkowy po stronie serwera. Wyniki nowej ery mają `resultType`, a serwer powinien podawać `io.modelcontextprotocol/serverInfo` w `_meta` odpowiedzi.

Jaźń zachowuje starszy handshake jako osobną ścieżkę kompatybilności. Stan legacy nie jest używany do autoryzacji ani interpretacji requestu `2026-07-28`, dzięki czemu nowa ścieżka pozostaje per-request/stateless na poziomie MCP.

Tasks nie są już eksperymentalnym core z 2025 roku: współczesne Tasks są osobnym rozszerzeniem `io.modelcontextprotocol/tasks`. Wersja 5.77 celowo nie reklamuje tego rozszerzenia i odrzuca `tasks/*` w nowoczesnej ścieżce, dopóki pełny aktualny lifecycle nie zostanie zaimplementowany i zweryfikowany.

## Podstawa techniczna

1. **MCP 2026-07-28 — core / discovery / changelog**: stateless per-request metadata, `server/discover`, `resultType`, `serverInfo`, deterministic/cacheable list endpoints.
   - https://modelcontextprotocol.io/specification/2026-07-28/basic
   - https://modelcontextprotocol.io/specification/2026-07-28/server/discover
   - https://modelcontextprotocol.io/specification/2026-07-28/changelog
2. **MCP Tasks extension**: aktualny model Tasks jest osobnym rozszerzeniem, a nie capability, którą można deklarować częściowo.
   - https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks
3. **RFC 9110 §9.2.2**: automatyczny retry operacji nie-idempotentnej wymaga znajomości jej semantyki albo dowodu, że poprzednia próba nie została zastosowana. To uzasadnia prealokowane `request_id` i resume zamiast replayu.
   - https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods
4. **W3C Trace Context**: przenośny format korelacji requestu przez komponenty; MCP 2026 rezerwuje `traceparent`, `tracestate` i `baggage` dla OpenTelemetry/W3C.
   - https://www.w3.org/TR/trace-context/
5. **OpenAI Responses API**: `prompt_cache_key` i `allowed_tools`/ToolChoiceAllowed są częścią aktualnego API.
   - https://developers.openai.com/api/reference/resources/responses/methods/create
6. **OpenAI prompt caching**: cache wymaga wspólnego prefixu; stabilne instrukcje/przykłady powinny być z przodu, a zmienna treść bliżej końca.
   - https://openai.com/index/unrolling-the-codex-agent-loop/
7. **Google SRE**: retry mogą wzmacniać awarie; powinny być ograniczone i kontrolowane zamiast tworzyć retry storm.
   - https://sre.google/sre-book/service-best-practices/
8. **ReAct (Yao et al.)**: model może planować użycie narzędzi, ale środowisko powinno wykonywać jawne akcje i zwracać obserwacje. W Jaźni model pozostaje plannerem, a runtime właścicielem wykonania i finalizacji.
   - https://arxiv.org/abs/2210.03629

## Granica tej aktualizacji

Kod nie twierdzi, że repozytorium może samo utworzyć executor ChatGPT, Secure MCP Tunnel control plane ani opublikować connector. Gdy host dostarcza zweryfikowaną aplikację/connector i działający transport, trasa remote jest preferowana. Bez takiego dowodu system pozostaje fail-closed zamiast imitować odpowiedź Jaźni.
