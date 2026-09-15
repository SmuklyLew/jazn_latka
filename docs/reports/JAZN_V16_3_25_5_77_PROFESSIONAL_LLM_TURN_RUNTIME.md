# Jaźń v16.3.25.5.77 — professional LLM turn runtime

## Cel

Ta aktualizacja porządkuje warstwę rozmowy ChatGPT/MCP bez tworzenia drugiego runtime i bez przenoszenia lifecycle z `main.py`. Główną zmianą jest typed turn runtime, który nadaje jedną semantykę trasie wykonania, `request_id`, fazom tury, odzyskiwaniu po niejednoznacznym błędzie transportu i warunkom widocznego wyniku.

## Zmiany kodu

- `latka_jazn/runtime/turn_runtime.py`
  - `ExecutionRoute`, `TurnAction`, `TurnPhase` i jawna tabela legalnych przejść;
  - `TurnIdentity` z fingerprintem wiadomości oraz transportowym `traceparent` zgodnym formatem W3C Trace Context;
  - remote-first routing tylko przy łącznym dowodzie `process_running + healthy + ready + host connector capability`;
  - fail-closed walidacja `display_exact`, `generate_then_finalize` i `poll_runtime`;
  - retry policy: side-effecting submit nigdy nie jest automatycznie replayowany, a odzyskanie używa tego samego `request_id`.
- `latka_jazn/mcp/turn_runtime_adapter.py`
  - wiąże oczekiwaną tożsamość requestu z JSON-RPC/MCP przed zaufaniem odpowiedzi;
  - wykrywa mismatch request identity i zamienia go w `host_diagnostic` zamiast kontynuować niespójną turę;
  - dołącza typed directive, retry semantics i trace correlation do prywatnego `_meta`.
- `latka_jazn/mcp/server.py`
  - zachowuje v76 jako właściciela wykonania tooli, auth, audytu i idempotencji;
  - dodaje eksperymentalną capability `io.jazn/turn-runtime`;
  - nie reklamuje MCP Tasks 2025-11-25 dopóki pełny standard `list/get/result/cancel` nie jest wdrożony;
  - wzmacnia instrukcję hosta: generate raz, potem poll/resume tego samego requestu, finalizacja przed widocznym tekstem.

## Podstawa techniczna

1. **RFC 9110 §9.2.2 — Idempotent Methods**: klient nie powinien automatycznie ponawiać nie-idempotentnej operacji, chyba że zna jej semantykę jako idempotentną albo potrafi ustalić, że poprzednia próba nie została zastosowana. To uzasadnia prealokowane `request_id` i recovery przez poll/resume zamiast replayu `POST`.
   - https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods
2. **MCP 2025-11-25 — Tasks**: standard definiuje trwałe state machine, polling, `tasks/result`, terminalne stany i capability negotiation. Obecny starszy adapter Jaźni nie spełnia pełnego standardu, dlatego 16.3.25.5.77 nadal nie deklaruje standard Tasks.
   - https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks
3. **W3C Trace Context**: standard definiuje przenośny `traceparent` do korelacji jednego requestu przez wiele komponentów. Aktualizacja używa kompatybilnego formatu wyłącznie do korelacji transportowej i nie umieszcza w nim treści użytkownika.
   - https://www.w3.org/TR/trace-context/
4. **Google SRE — Production Services Best Practices**: retry mogą wzmacniać awarie i powodować cascading failures; retry powinny być ograniczone, z backoff/jitter i budżetem. Jaźń zachowuje istniejący retry budget w gatewayu, natomiast typed runtime jawnie zabrania automatycznego retry side-effecting submitu.
   - https://sre.google/sre-book/service-best-practices/
5. **OpenAI — aplikacje w ChatGPT**: niestandardowe aplikacje mogą udostępniać narzędzia przez MCP; publikacja/połączenie aplikacji jest osobną capability hosta i nie może zostać „wyprodukowana” przez sam pakiet SYSTEM.
   - https://help.openai.com/pl-pl/articles/11487775
6. **ReAct (Yao et al., 2022)**: rozdzielenie rozumowania i działań na narzędzia wspiera systemy, w których model planuje, a środowisko wykonuje jawne akcje i dostarcza dowody. Aktualizacja pozostawia LLM za adapterem modelu, a wykonanie/stan tury utrzymuje deterministyczny runtime.
   - https://arxiv.org/abs/2210.03629

## Granica tej aktualizacji

Kod nie twierdzi, że repozytorium może samo utworzyć executor ChatGPT ani opublikować connector. Gdy host udostępnia zweryfikowaną aplikację/connector i gotowy Secure MCP Tunnel, trasa remote jest preferowana. Gdy jej nie ma, runtime pozostaje fail-closed zamiast imitować odpowiedź Jaźni.
