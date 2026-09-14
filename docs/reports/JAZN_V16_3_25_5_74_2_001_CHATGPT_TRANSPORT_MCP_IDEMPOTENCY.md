# Jaźń v16.3.25.5.74.2.001 — ChatGPT transport + MCP idempotency convergence

## Cel

Ta aktualizacja usuwa klasę błędów, w której utrata odpowiedzi transportowej po możliwym submit mogła odłączyć host od właściwej tury albo skłonić warstwę hosta do ponownego wysłania tej samej wiadomości. Zakres jest celowo oddzielony od aktywnej pracy nad **Jaźń Studio Pamięci**: branch transportowy nie zmienia modułów `memory_rebuild_app`, narzędzi Studio ani schematów pamięci.

Wersja: `16.3.25.5.74.2.001-chatgpt-transport-mcp-idempotency`.

## Model awarii

Rozdzielone są trzy sytuacje:

1. **błąd hosta przed dowodem spawn** — np. `caas.internal.errors.TransportTimeoutError`; lokalny kod mógł w ogóle nie wystartować, więc filesystem/paczka/runtime pozostają nieweryfikowane;
2. **utrata odpowiedzi po możliwym przekroczeniu granicy skutku ubocznego** — submit mógł zostać przyjęty przez daemon, dlatego wynik jest niejednoznaczny i wolno wyłącznie poll/resume tego samego `request_id`;
3. **błąd wykonania już istniejącego requestu** — runtime/daemon zwraca własny stan terminalny i host nie może klasyfikować go jako awarii executora.

Ta separacja jest zgodna z zasadą idempotentnego client token: identyfikator żądania powstaje przed operacją i jest ponownie używany po niejednoznacznym wyniku, zamiast tworzyć drugą operację.

## Zmiany

### 1. Loader / ingress

`docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` pozostaje cienkim loaderem, ale jawnie wiąże:

- `TransportTimeoutError` przed spawn z `host_executor_unavailable` wyłącznie dla konkretnej powierzchni;
- non-streaming CLI z `--daemon-request-id` przydzielonym przed spawnem;
- odzyskanie z `--daemon-result <same-request-id>`;
- MCP z `jazn_generate_visible_reply(request_id=...)` oraz `jazn_resume_visible_reply(daemon_request_id=...)`;
- zakaz replayu wiadomości po niejednoznacznym submit.

### 2. SecureHostRuntimeGateway

`SecureHostRuntimeGateway.chat()` otrzymuje `request_id`, normalizuje go **przed** POST `/chat` i przekazuje daemonowi.

Jeżeli transport MCP→daemon zwróci `daemon_unavailable:*` po możliwym submit, gateway nie ponawia POST i nie tworzy nowej tury. Zwraca kanoniczny `poll_runtime` z tym samym `daemon_request_id`, `submit_outcome_authoritative=false` i `must_not_resubmit_user_message=true`.

Zwykły daemonowy ACK `done=false` / `queued|running` również jest normalizowany do `poll_runtime`, a nie do ogólnego błędu hosta.

### 3. MCP ingress identity

`JaznMcpServer` teraz łączy idempotency MCP z idempotency daemonu:

- jawny tool `request_id` ma pierwszeństwo;
- jeżeli go brak, JSON-RPC request `id` jest mapowany deterministycznie i namespacowany przez uwierzytelniony subject do bezpiecznego `mcp-<hash>`;
- gdy nie ma także JSON-RPC id, jeden UUID jest mintowany **przed dispatch**;
- ten sam identyfikator służy jako MCP request identity i jest przekazywany do daemonu.

Dzięki temu warstwa MCP nie może już zachować jednego klucza idempotencji lokalnie, a równocześnie utworzyć innego requestu w daemonie.

Jeżeli retry trafia na już zajęty klucz idempotencji bez zapisanego wyniku, serwer próbuje wznowić istniejący `daemon_request_id`; nie wykonuje ponownie `jazn_generate_visible_reply`.

### 4. Idempotent resume

`jazn_resume_visible_reply` traktuje przejściowy `daemon_unavailable:*` podczas poll jako nadal niejednoznaczny transport. Zwraca `poll_runtime` dla tego samego requestu i zachowuje zakaz ponownego wysłania wiadomości.

Błędy autorytatywne (`daemon_rejected:*`, mismatch bindingu, zużyty/wygaśnięty continuation) nadal kończą się fail-closed `host_diagnostic`.

### 5. Memory-recall ingress ordering

Bramka `run_host_pre_response_gate()` rozpoznaje `poll_runtime` **przed** content-level walidacją pamięci. To naprawia przypadek typu „Spoko. A co pamiętasz?”: dopóki runtime zwraca tylko stan pending, nie istnieje jeszcze wynik recall, który można ocenić pod kątem provenance. Pending nie jest więc fałszywie zamieniany na `memory_recall_observability_missing`.

Po uzyskaniu właściwego wyniku tury wszystkie dotychczasowe memory truth gates nadal obowiązują bez osłabienia.

## Inwarianty bezpieczeństwa

- jeden logical user turn = jeden prealokowany `request_id`;
- po możliwym submit transport ambiguity => poll/resume samego id;
- brak fallbacku do drugiej lokalnej tury po wyborze daemonu;
- MCP jest transportem do istniejącego persistent runtime, nie drugim runtime;
- `display_exact` pozostaje jedyną zgodą na runtime-owned visible reply;
- finalizacja, continuation binding, `turn_id`, `trace_id` i contract hash nie są osłabione;
- brak zmian w pamięci użytkowej i brak zmian w Jaźń Studio Pamięci.

## Testy regresyjne

Nowy `tests/test_chatgpt_transport_timeout_mcp_idempotency.py` obejmuje:

1. dokładnie nazwany `TransportTimeoutError` na daemon submit i zachowanie prealokowanego request id;
2. `TransportTimeoutError` w Secure MCP gateway => `poll_runtime` tego samego id;
3. zwykły pending ACK MCP => `poll_runtime`, bez nowej tury;
4. pytanie wymagające recall w stanie pending nie jest klasyfikowane jako brak pamięci;
5. timeout podczas `jazn_resume_visible_reply` zachowuje istniejący request;
6. stabilne i subject-scoped mapowanie JSON-RPC id na daemon request id;
7. propagację request id przez `JaznMcpServer._dispatch` do gateway;
8. aktywny loader zawiera kontrakt `TransportTimeoutError`, `--daemon-request-id`, `--daemon-result`, generate/resume i zakaz replayu.

## Interakcja z Jaźń Studio Pamięci

W chwili rozpoczęcia pracy branch `fix/v16.3.25.5.75-jazn-studio-pamieci-master73-convergence-next-step` był `15` commitów przed bieżącym `master` i `0` commitów za nim; merge-base był dokładnie `master @ 9d38a294c0479078e75b6385c8d46561c5d055c7`.

Ta aktualizacja nie dotyka plików `latka_jazn/tools/memory_rebuild_app/*`, `tools/jazn_memory_studio.py`, testów Studio ani jego dokumentacji. Potencjalny konflikt równoległego merge dotyczy wyłącznie `latka_jazn/version.py` i generowanych metadanych release, które powinny być rozstrzygane przez finalny numer wersji i kanoniczny metadata sync po wybraniu kolejności merge.

## Źródła projektowe i zewnętrzne

Projekt:

- `AGENTS.md`
- `AGENTS.codex.md`
- `AGENTS.chatgpt.md`
- `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt`
- `latka_jazn/core/turn_authority_runtime_overlay.py`
- `latka_jazn/core/chatgpt_host_pending_store.py`
- `latka_jazn/mcp/server.py`
- `latka_jazn/mcp/tunnel_bootstrap.py`

Źródła zewnętrzne wykorzystane do projektu retry/idempotency/transportu:

- OpenAI Secure MCP Tunnel (`openai/tunnel-client`): https://github.com/openai/tunnel-client
- Model Context Protocol — transports: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- AWS Builders' Library — Making retries safe with idempotent APIs: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- Microsoft Azure — Transient fault handling: https://learn.microsoft.com/en-us/azure/architecture/best-practices/transient-faults

Kluczowa wspólna zasada tych źródeł: retry operacji ze skutkiem ubocznym wymaga stabilnej tożsamości/idempotencji, a warstwy retry nie powinny się mnożyć i odtwarzać operacji bez wiedzy, czy poprzednia próba została wykonana.
